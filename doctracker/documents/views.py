from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib import messages
from django.db.models import Q, Count
from .models import Document, Category, DocumentHistory, Comment
from .forms import DocumentForm, CategoryForm, CommentForm, DocumentFilterForm


def is_htmx(request):
    return request.headers.get('HX-Request') == 'true'


def can_manage_document(user, document):
    return user.is_staff or user.is_superuser or document.created_by_id == user.id


def can_manage_categories(user):
    return user.is_staff or user.is_superuser


def get_manageable_document_or_404(request, pk):
    docs = Document.objects.all()
    if not request.user.is_staff and not request.user.is_superuser:
        docs = docs.filter(created_by=request.user)
    return get_object_or_404(docs, pk=pk)


def get_categories():
    return Category.objects.annotate(doc_count=Count('document')).order_by('name')


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        form = AuthenticationForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('dashboard')
    else:
        form = AuthenticationForm()
    return render(request, 'auth/login.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('login')


def register_view(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f'Account created for {user.username}!')
            return redirect('dashboard')
    else:
        form = UserCreationForm()
    return render(request, 'auth/register.html', {'form': form})


@login_required
def dashboard(request):
    docs = Document.objects.select_related('category', 'created_by', 'assigned_to')
    stats = {
        'total': docs.count(),
        'draft': docs.filter(status='draft').count(),
        'review': docs.filter(status='review').count(),
        'approved': docs.filter(status='approved').count(),
        'archived': docs.filter(status='archived').count(),
        'my_docs': docs.filter(created_by=request.user).count(),
        'assigned_to_me': docs.filter(assigned_to=request.user).count(),
    }
    recent = list(docs.order_by('-updated_at')[:8])
    for doc in recent:
        doc.can_manage = can_manage_document(request.user, doc)
    return render(request, 'documents/dashboard.html', {'stats': stats, 'recent': recent})


@login_required
def document_list(request):
    form = DocumentFilterForm(request.GET)
    docs = Document.objects.select_related('category', 'created_by', 'assigned_to')

    if form.is_valid():
        if q := form.cleaned_data.get('search'):
            docs = docs.filter(
                Q(title__icontains=q) |
                Q(description__icontains=q) |
                Q(tags__icontains=q) |
                Q(file__icontains=q)
            )
        if s := form.cleaned_data.get('status'):
            docs = docs.filter(status=s)
        if c := form.cleaned_data.get('category'):
            docs = docs.filter(category=c)
        if u := form.cleaned_data.get('assigned_to'):
            docs = docs.filter(assigned_to=u)

    count = docs.count()
    docs = list(docs)
    for doc in docs:
        doc.can_manage = can_manage_document(request.user, doc)

    template = 'documents/_document_results.html' if is_htmx(request) else 'documents/list.html'
    return render(request, template, {
        'docs': docs,
        'form': form,
        'count': count,
        'include_oob_count': is_htmx(request),
    })


@login_required
def document_create(request):
    if request.method == 'POST':
        form = DocumentForm(request.POST, request.FILES)
        if form.is_valid():
            doc = form.save(commit=False)
            doc.created_by = request.user
            doc.save()
            DocumentHistory.objects.create(
                document=doc, changed_by=request.user,
                change_note='Document created', new_status=doc.status
            )
            messages.success(request, 'Document created successfully.')
            return redirect('document_detail', pk=doc.pk)
    else:
        form = DocumentForm()
    return render(request, 'documents/form.html', {'form': form, 'title': 'Create Document'})


@login_required
def document_detail(request, pk):
    doc = get_object_or_404(Document, pk=pk)
    comment_form = CommentForm()
    comment_added = False
    if request.method == 'POST':
        comment_form = CommentForm(request.POST)
        if comment_form.is_valid():
            c = comment_form.save(commit=False)
            c.document = doc
            c.author = request.user
            c.save()
            if is_htmx(request):
                comment_form = CommentForm()
                comment_added = True
            else:
                messages.success(request, 'Comment added.')
                return redirect('document_detail', pk=pk)
    comments = doc.comments.select_related('author').all()
    context = {
        'doc': doc,
        'can_manage_doc': can_manage_document(request.user, doc),
        'comment_form': comment_form,
        'history': doc.history.select_related('changed_by').all(),
        'comments': comments,
        'comment_added': comment_added,
    }
    template = 'documents/_comments_panel.html' if is_htmx(request) and request.method == 'POST' else 'documents/detail.html'
    return render(request, template, context)


@login_required
def document_edit(request, pk):
    doc = get_manageable_document_or_404(request, pk)
    old_status = doc.status
    if request.method == 'POST':
        form = DocumentForm(request.POST, request.FILES, instance=doc)
        if form.is_valid():
            doc = form.save()
            note = f'Document updated'
            if old_status != doc.status:
                note = f'Status changed from {old_status} to {doc.status}'
            DocumentHistory.objects.create(
                document=doc, changed_by=request.user,
                change_note=note, old_status=old_status, new_status=doc.status
            )
            messages.success(request, 'Document updated.')
            return redirect('document_detail', pk=doc.pk)
    else:
        form = DocumentForm(instance=doc)
    return render(request, 'documents/form.html', {'form': form, 'title': 'Edit Document', 'doc': doc})


@login_required
def document_delete(request, pk):
    doc = get_manageable_document_or_404(request, pk)
    if request.method == 'POST':
        doc.delete()
        messages.success(request, 'Document deleted.')
        return redirect('document_list')
    return render(request, 'documents/confirm_delete.html', {'doc': doc})


@login_required
def category_list(request):
    categories = get_categories()
    form = CategoryForm()
    category_added = False
    category_error = ''
    if request.method == 'POST':
        if can_manage_categories(request.user):
            form = CategoryForm(request.POST)
            if form.is_valid():
                form.save()
                categories = get_categories()
                if is_htmx(request):
                    form = CategoryForm()
                    category_added = True
                else:
                    messages.success(request, 'Category added.')
                    return redirect('category_list')
        else:
            category_error = 'Only admins can manage categories.'
            if not is_htmx(request):
                messages.error(request, category_error)
                return redirect('category_list')
    template = 'documents/_category_grid.html' if is_htmx(request) else 'documents/categories.html'
    return render(request, template, {
        'categories': categories,
        'form': form,
        'category_added': category_added,
        'category_error': category_error,
        'can_manage_categories': can_manage_categories(request.user),
    })


@login_required
def category_delete(request, pk):
    cat = get_object_or_404(Category, pk=pk)
    if request.method == 'POST':
        if not can_manage_categories(request.user):
            if is_htmx(request):
                return render(request, 'documents/_category_grid.html', {
                    'categories': get_categories(),
                    'form': CategoryForm(),
                    'category_error': 'Only admins can manage categories.',
                    'can_manage_categories': False,
                })
            messages.error(request, 'Only admins can manage categories.')
            return redirect('category_list')
        cat.delete()
        if is_htmx(request):
            return render(request, 'documents/_category_grid.html', {
                'categories': get_categories(),
                'form': CategoryForm(),
                'can_manage_categories': can_manage_categories(request.user),
            })
        messages.success(request, 'Category deleted.')
    return redirect('category_list')
