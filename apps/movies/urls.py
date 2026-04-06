from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('movie/upload/', views.upload_movie, name='upload_movie'),
    path('movie/<slug:slug>/', views.movie_detail, name='movie_detail'),
    path('movie/<slug:slug>/review/', views.add_review, name='add_review'),
]
