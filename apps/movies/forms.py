from django import forms
from .models import Movie, Genre

class MovieForm(forms.ModelForm):
    class Meta:
        model = Movie
        fields = ['title', 'description', 'poster_path', 'release_date', 'duration', 'trailer_url', 'genres']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Movie Title'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Brief description...'}),
            'poster_path': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://image.tmdb.org/t/p/w500/...'}),
            'release_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'duration': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Minutes'}),
            'trailer_url': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'YouTube URL'}),
            'genres': forms.SelectMultiple(attrs={'class': 'form-control', 'style': 'height: 120px;'}),
        }
