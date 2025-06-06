from django.test import TestCase
from .models import KnowledgeBaseArticle

class KnowledgeBaseArticleModelTest(TestCase):
    def test_create_article(self):
        article = KnowledgeBaseArticle.objects.create(
            title="How to reset your password",
            content="Go to settings and click 'Reset Password'.",
            tags=["password", "account"]
        )
        self.assertEqual(article.title, "How to reset your password")
        self.assertIn("password", article.tags)
