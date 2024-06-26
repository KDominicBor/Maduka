# -*- coding: utf-8 -*-
import json

from django.core.cache import cache
from django.test import TestCase
from django.test.utils import override_settings

from oscar.apps.catalogue.categories import create_from_breadcrumbs
from oscar.apps.catalogue.models import Category
from oscar.templatetags.category_tags import get_annotated_list


class TestCategory(TestCase):
    def setUp(self):
        self.products = Category.add_root(name="Pröducts")
        self.books = self.products.add_child(name="Bücher")

    def tearDown(self):
        cache.clear()

    def test_includes_parents_name_in_full_name(self):
        self.assertTrue(self.products.name in self.books.full_name)

    def test_has_children_method(self):
        self.assertTrue(self.products.has_children())

    def test_slugs_were_autogenerated(self):
        self.assertTrue(self.products.slug)
        self.assertTrue(self.books.slug)

    def test_supplied_slug_is_not_altered(self):
        more_books = self.products.add_child(name=self.books.name, slug=self.books.slug)
        self.assertEqual(more_books.slug, self.books.slug)

    @override_settings(OSCAR_SLUG_ALLOW_UNICODE=True)
    def test_unicode_slug(self):
        root_category = Category.add_root(name="Vins français")
        child_category = root_category.add_child(name="Château d'Yquem")
        self.assertEqual(root_category.slug, "vins-français")
        self.assertEqual(
            root_category.get_absolute_url(),
            "/catalogue/category/vins-fran%C3%A7ais_{}/".format(root_category.pk),
        )
        self.assertEqual(child_category.slug, "château-dyquem")
        self.assertEqual(
            child_category.get_absolute_url(),
            "/catalogue/category/vins-fran%C3%A7ais/ch%C3%A2teau-dyquem_{}/".format(
                child_category.pk
            ),
        )

    @override_settings(OSCAR_SLUG_ALLOW_UNICODE=True)
    def test_url_caching(self):
        category = self.products.add_child(name="Fromages français")
        absolute_url = category.get_absolute_url()
        url = cache.get(category.get_url_cache_key())
        self.assertEqual(url, "products/fromages-français")
        self.assertEqual(
            absolute_url,
            "/catalogue/category/products/fromages-fran%C3%A7ais_{}/".format(
                category.pk
            ),
        )


class TestMovingACategory(TestCase):
    def setUp(self):
        breadcrumbs = (
            "Books > Fiction > Horror > Teen",
            "Books > Fiction > Horror > Gothic",
            "Books > Fiction > Comedy",
            "Books > Non-fiction > Biography",
            "Books > Non-fiction > Programming",
            "Books > Children",
        )
        for trail in breadcrumbs:
            create_from_breadcrumbs(trail)

        horror = Category.objects.get(name="Horror")
        programming = Category.objects.get(name="Programming")
        horror.move(programming)

        # Reload horror instance to pick up changes
        self.horror = Category.objects.get(name="Horror")

    def test_updates_instance_name(self):
        self.assertEqual("Books > Non-fiction > Horror", self.horror.full_name)

    def test_updates_subtree_names(self):
        teen = Category.objects.get(name="Teen")
        self.assertEqual("Books > Non-fiction > Horror > Teen", teen.full_name)
        gothic = Category.objects.get(name="Gothic")
        self.assertEqual("Books > Non-fiction > Horror > Gothic", gothic.full_name)

    def test_fix_tree(self):
        "fix_tree should rearrange the incorrect nodes and not cause any errors"
        cat = Category.objects.get(path="00010002")
        pk = cat.pk
        self.assertEqual(cat.path, "00010002")

        Category.objects.filter(pk=pk).update(path="00010050")
        cat.refresh_from_db()
        self.assertEqual(cat.path, "00010050")

        Category.fix_tree(fix_paths=True)
        cat.refresh_from_db()
        self.assertEqual(cat.path, "00010003")


class TestCategoryFactory(TestCase):
    def test_can_create_single_level_category(self):
        trail = "Books"
        category = create_from_breadcrumbs(trail)
        self.assertIsNotNone(category)
        self.assertEqual(category.name, "Books")
        self.assertEqual(category.slug, "books")

    def test_can_create_parent_and_child_categories(self):
        trail = "Books > Science-Fiction"
        category = create_from_breadcrumbs(trail)

        self.assertIsNotNone(category)
        self.assertEqual(category.name, "Science-Fiction")
        self.assertEqual(category.get_depth(), 2)
        self.assertEqual(category.get_parent().name, "Books")
        self.assertEqual(2, Category.objects.count())
        self.assertEqual(category.full_slug, "books/science-fiction")

    def test_can_create_multiple_categories(self):
        trail = "Books > Science-Fiction > Star Trek"
        create_from_breadcrumbs(trail)
        trail = "Books > Factual > Popular Science"
        category = create_from_breadcrumbs(trail)

        self.assertIsNotNone(category)
        self.assertEqual(category.name, "Popular Science")
        self.assertEqual(category.get_depth(), 3)
        self.assertEqual(category.get_parent().name, "Factual")
        self.assertEqual(5, Category.objects.count())
        self.assertEqual(
            category.full_slug,
            "books/factual/popular-science",
        )

    def test_can_use_alternative_separator(self):
        trail = "Food|Cheese|Blue"
        create_from_breadcrumbs(trail, separator="|")
        self.assertEqual(3, len(Category.objects.all()))

    def test_updating_subtree_slugs_when_moving_category_to_new_parent(self):
        trail = "A > B > C"
        create_from_breadcrumbs(trail)
        trail = "A > B > D"
        create_from_breadcrumbs(trail)
        trail = "A > E > F"
        create_from_breadcrumbs(trail)
        trail = "A > E > G"
        create_from_breadcrumbs(trail)

        trail = "T"
        target = create_from_breadcrumbs(trail)
        category = Category.objects.get(name="A")

        category.move(target, pos="first-child")

        c1 = Category.objects.get(name="A")
        self.assertEqual(c1.full_slug, "t/a")
        self.assertEqual(c1.full_name, "T > A")

        child = Category.objects.get(name="F")
        self.assertEqual(child.full_slug, "t/a/e/f")
        self.assertEqual(child.full_name, "T > A > E > F")

        child = Category.objects.get(name="D")
        self.assertEqual(child.full_slug, "t/a/b/d")
        self.assertEqual(child.full_name, "T > A > B > D")

    def test_updating_subtree_when_moving_category_to_new_sibling(self):
        trail = "A > B > C"
        create_from_breadcrumbs(trail)
        trail = "A > B > D"
        create_from_breadcrumbs(trail)
        trail = "A > E > F"
        create_from_breadcrumbs(trail)
        trail = "A > E > G"
        create_from_breadcrumbs(trail)

        category = Category.objects.get(name="E")
        target = Category.objects.get(name="A")

        category.move(target, pos="right")

        child = Category.objects.get(name="E")
        self.assertEqual(child.full_slug, "e")
        self.assertEqual(child.full_name, "E")

        child = Category.objects.get(name="F")
        self.assertEqual(child.full_slug, "e/f")
        self.assertEqual(child.full_name, "E > F")


class TestCategoryTemplateTags(TestCase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.template = """
          {% if tree_categories %}
              <ul>
              {% for tree_category, info in tree_categories %}
                  <li>
                  {% if tree_category.pk == category.pk %}
                      <strong>{{ tree_category.name }}</strong>
                  {% else %}
                      <a href="{{ tree_category.get_absolute_url }}">
                          {{ tree_category.name }}</a>
                  {% endif %}
                  {% if info.has_children %}<ul>{% else %}</li>{% endif %}
                  {% for n in info.num_to_close %}
                      </ul></li>
                  {% endfor %}
              {% endfor %}
              </ul>
          {% endif %}
        """

    def setUp(self):
        breadcrumbs = (
            "Books > Fiction > Horror > Teen",
            "Books > Fiction > Horror > Gothic",
            "Books > Fiction > Comedy",
            "Books > Non-fiction > Biography",
            "Books > Non-fiction > Programming",
            "Books > Children",
        )
        for trail in breadcrumbs:
            create_from_breadcrumbs(trail)

    def test_category_extra_info(self):
        annotated_list = get_annotated_list(depth=3)

        expected_categories_info = {
            "Books": {"has_children": True, "len_num_to_close": 0},
            "Fiction": {"has_children": True, "len_num_to_close": 0},
            "Horror": {"has_children": False, "len_num_to_close": 0},
            "Comedy": {"has_children": False, "len_num_to_close": 1},
            "Non-fiction": {"has_children": True, "len_num_to_close": 0},
            "Biography": {"has_children": False, "len_num_to_close": 0},
            "Programming": {"has_children": False, "len_num_to_close": 1},
            "Children": {"has_children": False, "len_num_to_close": 1},
        }
        actual_categories_info = {
            category.name: {
                "has_children": category.get("has_children", False),
                "len_num_to_close": len(category["num_to_close"]),
            }
            for category, _ in annotated_list
        }
        # json.dumps provide an easy way to compare nested dict
        self.assertEqual(
            json.dumps(expected_categories_info), json.dumps(actual_categories_info)
        )

    def get_category_names(self, depth=None, parent=None):
        """
        For the tests, we are only interested in the category names returned
        from the template tag. This helper calls the template tag and
        returns a list of the included categories.
        """
        annotated_list = get_annotated_list(depth, parent)
        names = [category.name for category, __ in annotated_list]

        names_set = set(names)
        # We return a set to ease testing, but need to be sure we're not
        # losing any duplicates through that conversion.
        self.assertEqual(len(names_set), len(names))
        return names_set

    def test_all_categories(self):
        expected_categories = {
            "Books",
            "Fiction",
            "Horror",
            "Teen",
            "Gothic",
            "Comedy",
            "Non-fiction",
            "Biography",
            "Programming",
            "Children",
        }
        actual_categories = self.get_category_names()
        self.assertEqual(expected_categories, actual_categories)

    def test_categories_depth(self):
        expected_categories = {"Books"}
        actual_categories = self.get_category_names(depth=1)
        self.assertEqual(expected_categories, actual_categories)

    def test_categories_parent(self):
        parent = Category.objects.get(name="Fiction")
        actual_categories = self.get_category_names(parent=parent)
        expected_categories = {"Horror", "Teen", "Gothic", "Comedy"}
        self.assertEqual(expected_categories, actual_categories)

    def test_categories_depth_parent(self):
        parent = Category.objects.get(name="Fiction")
        actual_categories = self.get_category_names(depth=1, parent=parent)
        expected_categories = {"Horror", "Comedy"}
        self.assertEqual(expected_categories, actual_categories)
