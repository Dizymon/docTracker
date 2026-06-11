from django import forms
from django.contrib.auth.models import User
from .models import Document, Category, Comment


class DocumentForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ['title', 'description', 'category', 'status', 'file', 'tags', 'assigned_to', 'due_date']
        widgets = {
            'due_date': forms.DateInput(attrs={'type': 'date'}),
            'description': forms.Textarea(attrs={'rows': 3}),
            'tags': forms.TextInput(attrs={'placeholder': 'e.g. finance, report, Q1'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['assigned_to'].queryset = User.objects.all()
        self.fields['assigned_to'].empty_label = "-- Unassigned --"
        self.fields['category'].empty_label = "-- No Category --"


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'description']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 2}),
        }


class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ['text']
        widgets = {
            'text': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Add a comment...'}),
        }
        labels = {'text': ''}


class DocumentFilterForm(forms.Form):
    search = forms.CharField(required=False, widget=forms.TextInput(attrs={'placeholder': 'Search documents...'}))
    status = forms.ChoiceField(required=False, choices=[('', 'All Statuses')] + Document.STATUS_CHOICES)
    category = forms.ModelChoiceField(required=False, queryset=Category.objects.all(), empty_label="All Categories")
    assigned_to = forms.ModelChoiceField(required=False, queryset=User.objects.all(), empty_label="All Users")
