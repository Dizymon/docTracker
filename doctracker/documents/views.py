from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib import messages
from django.db.models import Q, Count
from django.utils import timezone
from datetime import timedelta
from .models import Document, Category, DocumentHistory, DocumentFileVersion, Comment, UserProfile, user_has_role
from .forms import DocumentForm, CategoryForm, CommentForm, DocumentFilterForm


def is_htmx(request):
    return request.headers.get('HX-Request') == 'true'


def can_manage_document(user, document):
    if (
        user.is_staff or user.is_superuser or
        user_has_role(user, UserProfile.ROLE_ADMIN, UserProfile.ROLE_HR) or
        user.groups.filter(name__in=['Admin', 'Manager']).exists()
    ):
        return True
    if user.groups.filter(name='Viewer').exists():
        return False
    return (
        document.created_by_id == user.id or
        document.assigned_to_id == user.id
    )


def can_view_all_documents(user):
    return (
        user.is_staff or user.is_superuser or
        user_has_role(user, UserProfile.ROLE_ADMIN, UserProfile.ROLE_HR) or
        user.groups.filter(name__in=['Admin', 'Manager', 'Viewer']).exists()
    )


def can_view_document(user, document):
    return can_view_all_documents(user) or document.created_by_id == user.id or document.assigned_to_id == user.id


def can_manage_categories(user):
    return (
        user.is_staff or user.is_superuser or
        user_has_role(user, UserProfile.ROLE_ADMIN, UserProfile.ROLE_HR) or
        user.groups.filter(name__in=['Admin', 'Manager']).exists()
    )


def visible_documents(user):
    docs = Document.objects.select_related('category', 'created_by', 'assigned_to')
    if can_view_all_documents(user):
        return docs
    return docs.filter(Q(created_by=user) | Q(assigned_to=user))


def get_manageable_document_or_404(request, pk):
    return get_object_or_404(visible_documents(request.user), pk=pk)


def create_file_version(document, user, note=''):
    if document.file:
        DocumentFileVersion.objects.create(
            document=document,
            file=document.file,
            uploaded_by=user,
            note=note,
        )


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
            UserProfile.objects.get_or_create(user=user)
            login(request, user)
            messages.success(request, f'Account created for {user.username}!')
            return redirect('dashboard')
    else:
        form = UserCreationForm()
    return render(request, 'auth/register.html', {'form': form})


@login_required
def dashboard(request):
    docs = visible_documents(request.user)
    today = timezone.localdate()
    soon = today + timedelta(days=7)
    stats = {
        'total': docs.count(),
        'draft': docs.filter(status='draft').count(),
        'review': docs.filter(status='review').count(),
        'approved': docs.filter(status='approved').count(),
        'archived': docs.filter(status='archived').count(),
        'my_docs': docs.filter(created_by=request.user).count(),
        'assigned_to_me': docs.filter(assigned_to=request.user).count(),
        'overdue': docs.filter(due_date__lt=today).exclude(status__in=['approved', 'archived']).count(),
        'due_soon': docs.filter(due_date__range=(today, soon)).exclude(status__in=['approved', 'archived']).count(),
        'high_priority': docs.filter(priority__in=['high', 'urgent']).count(),
    }
    dashboard_filter = request.GET.get('filter', '')
    filtered_docs = docs
    if dashboard_filter == 'assigned':
        filtered_docs = filtered_docs.filter(assigned_to=request.user)
    elif dashboard_filter == 'mine':
        filtered_docs = filtered_docs.filter(created_by=request.user)
    elif dashboard_filter == 'overdue':
        filtered_docs = filtered_docs.filter(due_date__lt=today).exclude(status__in=['approved', 'archived'])
    elif dashboard_filter == 'soon':
        filtered_docs = filtered_docs.filter(due_date__range=(today, soon)).exclude(status__in=['approved', 'archived'])
    elif dashboard_filter == 'priority':
        filtered_docs = filtered_docs.filter(priority__in=['high', 'urgent'])
    recent = list(filtered_docs.order_by('-updated_at')[:8])
    for doc in recent:
        doc.can_manage = can_manage_document(request.user, doc)
    return render(request, 'documents/dashboard.html', {
        'stats': stats,
        'recent': recent,
        'dashboard_filter': dashboard_filter,
    })


@login_required
def document_list(request):
    form = DocumentFilterForm(request.GET)
    docs = visible_documents(request.user)
    today = timezone.localdate()
    soon = today + timedelta(days=7)

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
        if p := form.cleaned_data.get('priority'):
            docs = docs.filter(priority=p)
        if d := form.cleaned_data.get('due'):
            if d == 'overdue':
                docs = docs.filter(due_date__lt=today).exclude(status__in=['approved', 'archived'])
            elif d == 'soon':
                docs = docs.filter(due_date__range=(today, soon)).exclude(status__in=['approved', 'archived'])
            elif d == 'none':
                docs = docs.filter(due_date__isnull=True)
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
        form = DocumentForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            doc = form.save(commit=False)
            doc.created_by = request.user
            doc.save()
            create_file_version(doc, request.user, 'Initial upload')
            DocumentHistory.objects.create(
                document=doc, changed_by=request.user,
                change_type='created', change_note='Document created', new_status=doc.status
            )
            messages.success(request, 'Document created successfully.')
            return redirect('document_detail', pk=doc.pk)
    else:
        form = DocumentForm(user=request.user)
    return render(request, 'documents/form.html', {'form': form, 'title': 'Create Document'})


@login_required
def document_detail(request, pk):
    doc = get_object_or_404(visible_documents(request.user), pk=pk)
    comment_form = CommentForm()
    comment_added = False
    if request.method == 'POST':
        comment_form = CommentForm(request.POST)
        if comment_form.is_valid():
            c = comment_form.save(commit=False)
            c.document = doc
            c.author = request.user
            c.save()
            DocumentHistory.objects.create(
                document=doc,
                changed_by=request.user,
                change_type='comment',
                change_note=f'Comment added: {c.text[:120]}',
                old_status=doc.status,
                new_status=doc.status,
            )
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
        'file_versions': doc.file_versions.select_related('uploaded_by').all(),
        'comment_added': comment_added,
    }
    template = 'documents/_comments_panel.html' if is_htmx(request) and request.method == 'POST' else 'documents/detail.html'
    return render(request, template, context)


@login_required
def document_edit(request, pk):
    doc = get_manageable_document_or_404(request, pk)
    if not can_manage_document(request.user, doc):
        messages.error(request, 'You do not have permission to edit this document.')
        return redirect('document_detail', pk=doc.pk)
    old_status = doc.status
    old_file = doc.file
    if request.method == 'POST':
        form = DocumentForm(request.POST, request.FILES, instance=doc, user=request.user)
        if form.is_valid():
            doc = form.save(commit=False)
            if form.fields['status'].disabled:
                doc.status = old_status
            if form.fields['file'].disabled:
                doc.file = old_file
            doc.save()
            status_note = form.cleaned_data.get('status_note', '').strip()
            note = f'Document updated'
            change_type = 'updated'
            if old_status != doc.status:
                note = f'Status changed from {old_status} to {doc.status}: {status_note}'
                change_type = 'status'
            if old_file != doc.file and doc.file:
                create_file_version(doc, request.user, 'Replacement upload')
                DocumentHistory.objects.create(
                    document=doc, changed_by=request.user,
                    change_type='file', change_note='File replaced',
                    old_status=old_status, new_status=doc.status
                )
            DocumentHistory.objects.create(
                document=doc, changed_by=request.user,
                change_type=change_type, change_note=note, old_status=old_status, new_status=doc.status
            )
            messages.success(request, 'Document updated.')
            return redirect('document_detail', pk=doc.pk)
    else:
        form = DocumentForm(instance=doc, user=request.user)
    return render(request, 'documents/form.html', {'form': form, 'title': 'Edit Document', 'doc': doc})


@login_required
def document_delete(request, pk):
    doc = get_manageable_document_or_404(request, pk)
    if not can_manage_document(request.user, doc):
        messages.error(request, 'You do not have permission to delete this document.')
        return redirect('document_detail', pk=doc.pk)
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
