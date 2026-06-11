from django.contrib import admin
from .models import Document, Category, DocumentHistory, Comment

admin.site.register(Document)
admin.site.register(Category)
admin.site.register(DocumentHistory)
admin.site.register(Comment)
