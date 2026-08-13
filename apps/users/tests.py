"""
Tests for Feature 7: Password Reset Security.
"""

from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIRequestFactory
from django.core.cache import cache

from apps.users.views import reset_password, confirm_reset_password

User = get_user_model()


class PasswordResetSecurityTests(TestCase):
    def setUp(self):
        cache.clear()
        self.factory = APIRequestFactory()
        self.user = User.objects.create_user(
            username="secureuser",
            email="secure@example.com",
            password="oldpassword123",
        )

    def test_enumeration_prevention(self):
        """Same response for existing and non-existing emails."""
        req1 = self.factory.post("/reset/", {"email": "secure@example.com"})
        res1 = reset_password(req1)

        req2 = self.factory.post("/reset/", {"email": "nobody@example.com"})
        res2 = reset_password(req2)

        self.assertEqual(res1.status_code, res2.status_code)
        self.assertEqual(res1.data, res2.data)

    def test_token_not_plaintext_in_db(self):
        """Token stored as hash, not raw."""
        req = self.factory.post("/reset/", {"email": "secure@example.com"})
        reset_password(req)

        # Fetch fresh from DB to avoid any instance-level caching/signal side-effects
        user = User.objects.get(email="secure@example.com")
        self.assertEqual(len(user.reset_token), 64)  # SHA256 hex
        self.assertFalse(user.reset_token.isdigit())

    def test_token_expiration_set(self):
        req = self.factory.post("/reset/", {"email": "secure@example.com"})
        reset_password(req)

        user = User.objects.get(email="secure@example.com")
        self.assertIsNotNone(user.reset_token_expires_at)