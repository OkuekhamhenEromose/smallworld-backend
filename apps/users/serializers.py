"""
Serializers for user-related endpoints.
"""

from rest_framework import serializers


class PasswordResetRequestSerializer(serializers.Serializer):
    """
    Validates password reset request.
    No user-facing validation errors that reveal email existence.
    """
    email = serializers.EmailField(required=True, max_length=255)

    def validate_email(self, value):
        return value.lower().strip()