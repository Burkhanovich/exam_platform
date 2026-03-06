from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.contrib import messages
from django.views.decorators.http import require_POST
from .models import CustomUser, StudentGroup


def user_login(request):
    """Login view"""
    if request.user.is_authenticated:
        return redirect('exams:exam_list')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            messages.success(request, f"Xush kelibsiz, {user.get_full_name()}!")
            return redirect('exams:exam_list')
        else:
            messages.error(request, "Login yoki parol noto'g'ri!")
    
    return render(request, 'users/login.html')


@require_POST
def user_logout(request):
    """Logout view"""
    logout(request)
    messages.info(request, "Tizimdan muvaffaqiyatli chiqdingiz!")
    return redirect('users:login')


def user_register(request):
    """Register view"""
    if request.user.is_authenticated:
        return redirect('exams:exam_list')
    
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')
        password2 = request.POST.get('password2', '')
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        
        if not username:
            messages.error(request, "Username kiritilishi shart!")
            return render(request, 'users/register.html')
        
        if password != password2:
            messages.error(request, "Parollar mos emas!")
            return render(request, 'users/register.html')
        
        # Parol validatsiyasi
        try:
            validate_password(password)
        except ValidationError as e:
            for error in e.messages:
                messages.error(request, error)
            return render(request, 'users/register.html')
        
        if CustomUser.objects.filter(username=username).exists():
            messages.error(request, "Bu username band!")
            return render(request, 'users/register.html')

        user = CustomUser.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            user_type='student'
        )
        
        messages.success(request, "Ro'yxatdan o'tdingiz! Admin sizni guruhga biriktirgandan so'ng testlarni ko'rishingiz mumkin.")
        return redirect('users:login')
    
    return render(request, 'users/register.html')


@login_required
def user_profile(request):
    """User profile view"""
    return render(request, 'users/profile.html', {'user': request.user})


@login_required
def user_dashboard(request):
    """User dashboard view"""
    user = request.user
    
    context = {
        'user': user,
    }
    
    if user.user_type == 'student':
        from apps.results.models import ExamResult
        results = ExamResult.objects.filter(student=user).select_related('exam')
        context['results'] = results
        context['total_exams'] = results.count()
        
        if results.exists():
            context['avg_score'] = sum([r.percentage for r in results]) / results.count()
    
    elif user.user_type == 'teacher':
        from apps.exams.models import ExamAssignment, ExamGroupPermission
        context['assignments_count'] = ExamAssignment.objects.filter(teacher=user).count()
        context['permissions_count'] = ExamGroupPermission.objects.filter(teacher=user, is_active=True).count()
        context['total_groups'] = StudentGroup.objects.count()
    
    elif user.user_type == 'admin':
        from apps.exams.models import Exam, ExamAssignment
        context['total_exams'] = Exam.objects.filter(is_active=True).count()
        context['total_groups'] = StudentGroup.objects.count()
        context['total_students'] = CustomUser.objects.filter(user_type='student').count()
        context['total_teachers'] = CustomUser.objects.filter(user_type='teacher').count()
    
    return render(request, 'users/dashboard.html', context)
