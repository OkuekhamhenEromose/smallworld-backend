from django.urls import path
from . import views

# Placeholder — add post endpoints if needed
urlpatterns = [
    path("", views.post_list, name="post-list"),
]