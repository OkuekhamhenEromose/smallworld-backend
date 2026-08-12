from django.urls import path
from . import views

urlpatterns = [
    path("reset-password/", views.reset_password, name="reset-password"),
    path("confirm-reset/", views.confirm_reset_password, name="confirm-reset"),
]