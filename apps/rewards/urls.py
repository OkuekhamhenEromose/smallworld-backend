from django.urls import path
from . import views

urlpatterns = [
    path("<str:reward_id>/approve/", views.approve_reward, name="approve-reward"),
]