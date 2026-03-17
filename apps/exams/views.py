from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db import models, IntegrityError
from .models import Exam, ExamAttempt, ExamAssignment, ExamGroupPermission, Subject
from apps.questions.models import Question, Answer
from apps.results.models import ExamResult
from apps.users.models import StudentGroup, CustomUser, Notification


def _get_student_exams(user):
    """Studentga ruxsat berilgan imtihonlarni qaytaradi"""
    now = timezone.now()
    if not user.student_group:
        return Exam.objects.none()

    # Faqat guruhga ruxsat berilgan va deadline o'tmagan imtihonlar
    permitted_exam_ids = ExamGroupPermission.objects.filter(
        group=user.student_group,
        is_active=True,
        deadline__gte=now
    ).values_list('exam_id', flat=True)

    return Exam.objects.filter(
        id__in=permitted_exam_ids,
        is_active=True,
        start_time__lte=now,
    ).select_related('subject', 'created_by')


@login_required
def exam_list(request):
    """Imtihonlar ro'yxati"""
    user = request.user
    now = timezone.now()

    if user.user_type == 'student':
        exams = _get_student_exams(user)
    elif user.user_type == 'teacher':
        # O'qituvchiga tayinlangan imtihonlar
        assigned_exam_ids = ExamAssignment.objects.filter(
            teacher=user,
            admin_deadline__gte=now
        ).values_list('exam_id', flat=True)
        exams = Exam.objects.filter(
            id__in=assigned_exam_ids,
            is_active=True,
        ).select_related('subject', 'created_by')
    else:
        # Adminlar uchun barcha imtihonlar
        exams = Exam.objects.filter(is_active=True).select_related('subject', 'created_by')

    context = {
        'exams': exams,
        'now': now
    }

    return render(request, 'exams/exam_list.html', context)


@login_required
def exam_detail(request, exam_id):
    """Imtihon tafsilotlari"""
    exam = get_object_or_404(Exam, id=exam_id)
    user = request.user
    now = timezone.now()
    permission = None

    # Student uchun ruxsat tekshiruvi
    if user.user_type == 'student':
        if not user.student_group:
            messages.error(request, "Siz hech qanday guruhga biriktirilmagansiz!")
            return redirect('exams:exam_list')
        permission = ExamGroupPermission.objects.filter(
            exam=exam,
            group=user.student_group,
            is_active=True,
            deadline__gte=now
        ).first()
        if not permission:
            messages.error(request, "Sizga bu imtihon uchun ruxsat berilmagan!")
            return redirect('exams:exam_list')
        if not exam.is_active or exam.start_time > now:
            messages.error(request, "Bu imtihon hozirda mavjud emas!")
            return redirect('exams:exam_list')
    elif user.user_type == 'teacher':
        # O'qituvchi faqat o'ziga tayinlangan imtihonlarni ko'ra oladi
        assignment = ExamAssignment.objects.filter(
            exam=exam,
            teacher=user
        ).first()
        if not assignment:
            messages.error(request, "Bu imtihon sizga tayinlanmagan!")
            return redirect('exams:exam_list')
    
    # Student ushbu imtihonni olganligini tekshirish
    attempt = ExamAttempt.objects.filter(
        exam=exam,
        student=request.user
    ).first()
    
    context = {
        'exam': exam,
        'attempt': attempt,
        'questions_count': exam.get_questions_count(),
        'permission': permission,
    }
    
    return render(request, 'exams/exam_detail.html', context)


@login_required
def start_exam(request, exam_id):
    """Imtihonni boshlash"""
    exam = get_object_or_404(Exam, id=exam_id)
    user = request.user
    now = timezone.now()

    # Faqat studentlar imtihon topshira oladi
    if user.user_type != 'student':
        messages.error(request, "Faqat studentlar imtihon topshira oladi!")
        return redirect('exams:exam_detail', exam_id=exam.id)

    # Ruxsat tekshiruvi
    if not user.student_group:
        messages.error(request, "Siz hech qanday guruhga biriktirilmagansiz!")
        return redirect('exams:exam_list')

    permission = ExamGroupPermission.objects.filter(
        exam=exam,
        group=user.student_group,
        is_active=True,
        deadline__gte=now
    ).first()
    if not permission:
        messages.error(request, "Sizga bu imtihon uchun ruxsat berilmagan yoki muddati o'tgan!")
        return redirect('exams:exam_list')

    if not exam.is_active or exam.start_time > now:
        messages.error(request, "Bu imtihon hozirda mavjud emas!")
        return redirect('exams:exam_list')
    
    # Avval imtihon topshirilganligini tekshirish
    attempt = ExamAttempt.objects.filter(
        exam=exam,
        student=request.user
    ).first()
    
    if attempt:
        if attempt.status == 'completed':
            messages.info(request, "Siz bu imtihonni allaqachon topshirgansiz!")
            result = ExamResult.objects.filter(attempt=attempt).first()
            if result:
                return redirect('results:result_detail', result_id=result.id)
            return redirect('results:result_list')
        else:
            messages.info(request, "Imtihonni davom ettiryapsiz...")
            return redirect('exams:take_exam', exam_id=exam.id)
    
    # Yangi urinish yaratish (race condition himoyasi)
    try:
        attempt = ExamAttempt.objects.create(
            exam=exam,
            student=request.user,
            status='in_progress'
        )
    except IntegrityError:
        attempt = ExamAttempt.objects.filter(
            exam=exam,
            student=request.user
        ).first()
        return redirect('exams:take_exam', exam_id=exam.id)
    
    # Guruhga belgilangan vaqtni tekshirish
    group_duration = exam.duration
    if permission and permission.duration:
        group_duration = permission.duration

    messages.success(request, f"Imtihon boshlandi! Sizda {group_duration} daqiqa vaqt bor.")
    return redirect('exams:take_exam', exam_id=exam.id)


@login_required
def take_exam(request, exam_id):
    """Imtihon topshirish"""
    exam = get_object_or_404(Exam, id=exam_id)
    
    # Urinishni topish
    attempt = get_object_or_404(
        ExamAttempt,
        exam=exam,
        student=request.user,
        status='in_progress'
    )
    
    # Guruhga belgilangan vaqtni aniqlash
    effective_duration = exam.duration
    if request.user.student_group:
        group_perm = ExamGroupPermission.objects.filter(
            exam=exam,
            group=request.user.student_group,
            is_active=True
        ).first()
        if group_perm and group_perm.duration:
            effective_duration = group_perm.duration

    # Vaqt tugaganligini tekshirish
    questions = exam.questions.all().prefetch_related('answers')
    time_passed = (timezone.now() - attempt.started_at).total_seconds() / 60
    time_expired = time_passed > effective_duration
    
    if time_expired and request.method == 'GET':
        # Vaqt tugagan — mavjud javoblar asosida avtomatik baholash
        result = _grade_exam(exam, attempt, questions, request)
        messages.error(request, "Vaqt tugadi! Imtihon avtomatik yakunlandi.")
        return redirect('results:result_detail', result_id=result.id)
    
    if request.method == 'POST':
        # Javoblarni saqlash va baholash
        result = _grade_exam(exam, attempt, questions, request)
        messages.success(request, f"Imtihon yakunlandi! Sizning balingiz: {result.score:.1f}")
        return redirect('results:result_detail', result_id=result.id)
    
    time_remaining = effective_duration - time_passed
    
    context = {
        'exam': exam,
        'attempt': attempt,
        'questions': questions,
        'time_remaining': int(time_remaining)
    }
    
    return render(request, 'exams/take_exam.html', context)


def _grade_exam(exam, attempt, questions, request):
    """Imtihonni baholash yordamchi funksiyasi"""
    correct_answers = 0
    wrong_answers = 0
    score = 0
    total_questions = questions.count()
    question_ids = list(questions.values_list('id', flat=True))

    for question in questions:
        selected_answer_id = request.POST.get(f'question_{question.id}')
        if selected_answer_id:
            # Javob haqiqiyligini va ushbu savol ga tegishliligini tekshirish
            selected_answer = Answer.objects.filter(
                id=selected_answer_id,
                question_id=question.id
            ).first()
            if selected_answer and selected_answer.is_correct:
                correct_answers += 1
                score += question.marks
            else:
                wrong_answers += 1
        # Javob berilmagan savollar hisoblalmaydi (skip)

    # Urinishni yakunlash
    attempt.status = 'completed'
    attempt.completed_at = timezone.now()
    attempt.save()

    # Natijani saqlash
    result = ExamResult.objects.create(
        exam=exam,
        student=attempt.student,
        attempt=attempt,
        score=score,
        total_questions=total_questions,
        correct_answers=correct_answers,
        wrong_answers=wrong_answers,
        passed=score >= exam.passing_marks
    )
    return result


@login_required
def my_exams(request):
    """Mening imtihonlarim"""
    attempts = ExamAttempt.objects.filter(
        student=request.user
    ).select_related('exam', 'exam__subject').order_by('-started_at')
    
    context = {
        'attempts': attempts
    }
    
    return render(request, 'exams/my_exams.html', context)


# ===== O'QITUVCHI VIEWS =====

@login_required
def teacher_dashboard(request):
    """O'qituvchi boshqaruv paneli"""
    user = request.user
    if user.user_type not in ('teacher', 'admin'):
        messages.error(request, "Sizga bu sahifaga kirishga ruxsat yo'q!")
        return redirect('users:dashboard')

    now = timezone.now()

    # O'qituvchiga tayinlangan imtihonlar
    assignments = ExamAssignment.objects.filter(
        teacher=user
    ).select_related('exam', 'exam__subject', 'assigned_by').order_by('-created_at')

    # Guruh ruxsatlari
    permissions = ExamGroupPermission.objects.filter(
        teacher=user
    ).select_related('exam', 'exam__subject', 'group').order_by('-created_at')

    context = {
        'assignments': assignments,
        'permissions': permissions,
        'now': now,
    }
    return render(request, 'exams/teacher_dashboard.html', context)


@login_required
def grant_permission(request, assignment_id):
    """O'qituvchi guruhga imtihon uchun ruxsat beradi"""
    user = request.user
    if user.user_type not in ('teacher', 'admin'):
        messages.error(request, "Sizga bu sahifaga kirishga ruxsat yo'q!")
        return redirect('users:dashboard')

    assignment = get_object_or_404(ExamAssignment, id=assignment_id, teacher=user)
    now = timezone.now()

    # Admin deadline tekshiruvi
    if now > assignment.admin_deadline:
        messages.error(request, "Admin belgilagan muddat o'tib ketgan!")
        return redirect('exams:teacher_dashboard')

    # Admin start time tekshiruvi
    if assignment.admin_start_time and now < assignment.admin_start_time:
        messages.error(request, f"Ruxsat berish {assignment.admin_start_time.strftime('%d.%m.%Y %H:%M')} dan boshlab mumkin!")
        return redirect('exams:teacher_dashboard')

    groups = StudentGroup.objects.all()

    # Allaqachon ruxsat berilgan guruhlar
    existing_permissions = ExamGroupPermission.objects.filter(
        exam=assignment.exam,
        teacher=user
    ).select_related('group')
    existing_group_ids = set(existing_permissions.values_list('group_id', flat=True))

    if request.method == 'POST':
        group_id = request.POST.get('group_id')
        deadline_str = request.POST.get('deadline')
        duration_str = request.POST.get('duration', '').strip()

        if not deadline_str:
            messages.error(request, "Deadline tanlanishi shart!")
            return redirect('exams:grant_permission', assignment_id=assignment.id)

        # Vaqt (daqiqa) — majburiy
        if not duration_str:
            messages.error(request, "Test vaqti (daqiqa) kiritilishi shart!")
            return redirect('exams:grant_permission', assignment_id=assignment.id)

        group_duration = None
        try:
            group_duration = int(duration_str)
            if group_duration < 1:
                raise ValueError
        except ValueError:
            messages.error(request, "Vaqt (daqiqa) noto'g'ri kiritildi!")
            return redirect('exams:grant_permission', assignment_id=assignment.id)

        # Deadline parsing
        from datetime import datetime
        try:
            deadline = timezone.make_aware(datetime.strptime(deadline_str, '%Y-%m-%dT%H:%M'))
        except (ValueError, TypeError):
            messages.error(request, "Deadline formati noto'g'ri!")
            return redirect('exams:grant_permission', assignment_id=assignment.id)

        # Admin deadline'dan oshmasligi
        if deadline > assignment.admin_deadline:
            messages.error(request, f"Deadline admin muddatidan ({assignment.admin_deadline.strftime('%d.%m.%Y %H:%M')}) oshmasligi kerak!")
            return redirect('exams:grant_permission', assignment_id=assignment.id)

        # "Barcha guruhlar" tanlangan bo'lsa
        if group_id == 'all':
            target_groups = groups
            created_count = 0
            updated_count = 0
            for g in target_groups:
                perm, created = ExamGroupPermission.objects.update_or_create(
                    exam=assignment.exam,
                    group=g,
                    defaults={
                        'teacher': user,
                        'deadline': deadline,
                        'duration': group_duration,
                        'is_active': True,
                    }
                )
                if created:
                    created_count += 1
                else:
                    updated_count += 1
            msg_parts = []
            if created_count:
                msg_parts.append(f"{created_count} ta guruhga ruxsat berildi")
            if updated_count:
                msg_parts.append(f"{updated_count} ta guruh yangilandi")
            messages.success(request, f"Barcha guruhlar uchun '{assignment.exam.title}': {', '.join(msg_parts)}!")
        else:
            if not group_id:
                messages.error(request, "Guruh tanlanishi shart!")
                return redirect('exams:grant_permission', assignment_id=assignment.id)

            group = get_object_or_404(StudentGroup, id=group_id)

            # Yaratish yoki yangilash
            perm, created = ExamGroupPermission.objects.update_or_create(
                exam=assignment.exam,
                group=group,
                defaults={
                    'teacher': user,
                    'deadline': deadline,
                    'duration': group_duration,
                    'is_active': True,
                }
            )

            if created:
                messages.success(request, f"'{group.name}' guruhiga '{assignment.exam.title}' imtihoni uchun ruxsat berildi!")
            else:
                messages.success(request, f"'{group.name}' guruhi uchun ruxsat yangilandi!")

        return redirect('exams:teacher_dashboard')

    context = {
        'assignment': assignment,
        'groups': groups,
        'existing_permissions': existing_permissions,
        'existing_group_ids': existing_group_ids,
    }
    return render(request, 'exams/grant_permission.html', context)


@login_required
def revoke_permission(request, permission_id):
    """O'qituvchi guruh ruxsatini bekor qiladi"""
    user = request.user
    if user.user_type not in ('teacher', 'admin'):
        messages.error(request, "Sizga ruxsat yo'q!")
        return redirect('users:dashboard')

    perm = get_object_or_404(ExamGroupPermission, id=permission_id, teacher=user)
    group_name = perm.group.name
    exam_title = perm.exam.title
    perm.is_active = False
    perm.save()
    messages.success(request, f"'{group_name}' guruhi uchun '{exam_title}' imtihon ruxsati bekor qilindi!")
    return redirect('exams:teacher_dashboard')


@login_required
def teacher_results(request, exam_id):
    """O'qituvchi imtihon natijalarini ko'rish"""
    user = request.user
    if user.user_type not in ('teacher', 'admin'):
        messages.error(request, "Sizga ruxsat yo'q!")
        return redirect('users:dashboard')

    exam = get_object_or_404(Exam, id=exam_id)

    # O'qituvchiga tayinlanganligini tekshirish
    if user.user_type == 'teacher':
        assignment = ExamAssignment.objects.filter(exam=exam, teacher=user).first()
        if not assignment:
            messages.error(request, "Bu imtihon sizga tayinlanmagan!")
            return redirect('exams:teacher_dashboard')

    results = ExamResult.objects.filter(
        exam=exam
    ).select_related('student', 'student__student_group').order_by('-score')

    context = {
        'exam': exam,
        'results': results,
    }
    return render(request, 'exams/teacher_results.html', context)


# ===== O'QITUVCHI TEST YARATISH =====

@login_required
def teacher_create_exam(request):
    """O'qituvchi yangi test yaratadi (savollar va javoblar bilan birga)"""
    user = request.user
    if user.user_type not in ('teacher', 'admin'):
        messages.error(request, "Sizga bu sahifaga kirishga ruxsat yo'q!")
        return redirect('users:dashboard')

    subjects = Subject.objects.all()

    if request.method == 'POST':
        # Asosiy ma'lumotlar
        title = request.POST.get('title', '').strip()
        subject_id = request.POST.get('subject_id', '')
        exam_type = request.POST.get('exam_type', 'practice')
        description = request.POST.get('description', '').strip()
        total_marks = request.POST.get('total_marks', '').strip()
        passing_marks = request.POST.get('passing_marks', '').strip()

        # Validatsiya
        if not title or not subject_id:
            messages.error(request, "Test nomi va fan kiritilishi shart!")
            return render(request, 'exams/teacher_create_exam.html', {'subjects': subjects})

        try:
            subject = Subject.objects.get(id=subject_id)
        except Subject.DoesNotExist:
            messages.error(request, "Fan topilmadi!")
            return render(request, 'exams/teacher_create_exam.html', {'subjects': subjects})

        # Yangi fan yaratish (agar 'new_subject' tanlangan bo'lsa)
        new_subject_name = request.POST.get('new_subject_name', '').strip()
        if subject_id == 'new' and new_subject_name:
            subject, _ = Subject.objects.get_or_create(name=new_subject_name)

        from datetime import datetime, timedelta
        now = timezone.now()

        # Exam yaratish (duration=0, chunki vaqt guruhga biriktirilganda belgilanadi)
        exam = Exam.objects.create(
            title=title,
            subject=subject,
            exam_type=exam_type,
            description=description,
            duration=0,
            total_marks=int(total_marks) if total_marks else 100,
            passing_marks=int(passing_marks) if passing_marks else 60,
            start_time=now,
            end_time=now + timedelta(days=365),  # 1 yil davomida faol
            is_active=True,
            created_by=user,
        )

        # Savollar va javoblarni saqlash
        question_index = 1
        total_saved_marks = 0
        while True:
            q_text = request.POST.get(f'question_{question_index}_text', '').strip()
            if not q_text:
                break

            q_difficulty = request.POST.get(f'question_{question_index}_difficulty', 'medium')
            q_marks = request.POST.get(f'question_{question_index}_marks', '1')

            question = Question.objects.create(
                exam=exam,
                question_text=q_text,
                difficulty=q_difficulty,
                marks=int(q_marks) if q_marks else 1,
                order=question_index,
            )
            total_saved_marks += question.marks

            # Javoblarni saqlash
            answer_index = 1
            correct_answer = request.POST.get(f'question_{question_index}_correct', '')
            while True:
                a_text = request.POST.get(f'question_{question_index}_answer_{answer_index}', '').strip()
                if not a_text:
                    break

                Answer.objects.create(
                    question=question,
                    answer_text=a_text,
                    is_correct=(str(answer_index) == correct_answer),
                    order=answer_index,
                )
                answer_index += 1

            question_index += 1

        # Total marks ni haqiqiy qiymatga yangilash
        if total_saved_marks > 0:
            exam.total_marks = total_saved_marks
            exam.save()

        questions_count = exam.get_questions_count()
        messages.success(
            request,
            f"'{exam.title}' testi muvaffaqiyatli yaratildi! "
            f"{questions_count} ta savol qo'shildi."
        )
        return redirect('exams:teacher_my_tests')

    return render(request, 'exams/teacher_create_exam.html', {'subjects': subjects})


@login_required
def teacher_my_tests(request):
    """O'qituvchining yaratgan testlari ro'yxati"""
    user = request.user
    if user.user_type not in ('teacher', 'admin'):
        messages.error(request, "Sizga bu sahifaga kirishga ruxsat yo'q!")
        return redirect('users:dashboard')

    exams = Exam.objects.filter(
        created_by=user
    ).select_related('subject').order_by('-created_at')

    context = {
        'exams': exams,
    }
    return render(request, 'exams/teacher_my_tests.html', context)


@login_required
def teacher_edit_exam(request, exam_id):
    """O'qituvchi testni tahrirlash"""
    user = request.user
    if user.user_type not in ('teacher', 'admin'):
        messages.error(request, "Sizga ruxsat yo'q!")
        return redirect('users:dashboard')

    exam = get_object_or_404(Exam, id=exam_id, created_by=user)
    subjects = Subject.objects.all()
    questions = exam.questions.all().prefetch_related('answers').order_by('order')

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        subject_id = request.POST.get('subject_id', '')
        exam_type = request.POST.get('exam_type', 'practice')
        description = request.POST.get('description', '').strip()
        passing_marks = request.POST.get('passing_marks', '').strip()

        if not title or not subject_id:
            messages.error(request, "Test nomi va fan kiritilishi shart!")
            return redirect('exams:teacher_edit_exam', exam_id=exam.id)

        try:
            subject = Subject.objects.get(id=subject_id)
        except Subject.DoesNotExist:
            messages.error(request, "Fan topilmadi!")
            return redirect('exams:teacher_edit_exam', exam_id=exam.id)

        new_subject_name = request.POST.get('new_subject_name', '').strip()
        if subject_id == 'new' and new_subject_name:
            subject, _ = Subject.objects.get_or_create(name=new_subject_name)

        exam.title = title
        exam.subject = subject
        exam.exam_type = exam_type
        exam.description = description
        exam.passing_marks = int(passing_marks) if passing_marks else 60

        # Eski savollarni o'chirish va yangisini yaratish
        exam.questions.all().delete()

        question_index = 1
        total_saved_marks = 0
        while True:
            q_text = request.POST.get(f'question_{question_index}_text', '').strip()
            if not q_text:
                break

            q_difficulty = request.POST.get(f'question_{question_index}_difficulty', 'medium')
            q_marks = request.POST.get(f'question_{question_index}_marks', '1')

            question = Question.objects.create(
                exam=exam,
                question_text=q_text,
                difficulty=q_difficulty,
                marks=int(q_marks) if q_marks else 1,
                order=question_index,
            )
            total_saved_marks += question.marks

            answer_index = 1
            correct_answer = request.POST.get(f'question_{question_index}_correct', '')
            while True:
                a_text = request.POST.get(f'question_{question_index}_answer_{answer_index}', '').strip()
                if not a_text:
                    break

                Answer.objects.create(
                    question=question,
                    answer_text=a_text,
                    is_correct=(str(answer_index) == correct_answer),
                    order=answer_index,
                )
                answer_index += 1

            question_index += 1

        if total_saved_marks > 0:
            exam.total_marks = total_saved_marks
        exam.save()

        messages.success(request, f"'{exam.title}' testi muvaffaqiyatli yangilandi!")
        return redirect('exams:teacher_my_tests')

    # Mavjud savollar va javoblarni JSON ga aylantirish (template uchun)
    import json
    questions_data = []
    for q in questions:
        answers_list = []
        correct_idx = 1
        for idx, a in enumerate(q.answers.all().order_by('order'), 1):
            answers_list.append(a.answer_text)
            if a.is_correct:
                correct_idx = idx
        questions_data.append({
            'text': q.question_text,
            'difficulty': q.difficulty,
            'marks': q.marks,
            'answers': answers_list,
            'correct': correct_idx,
        })

    context = {
        'exam': exam,
        'subjects': subjects,
        'questions_json': json.dumps(questions_data, ensure_ascii=False),
    }
    return render(request, 'exams/teacher_edit_exam.html', context)


@login_required
def teacher_delete_exam(request, exam_id):
    """O'qituvchi testni o'chirish"""
    user = request.user
    if user.user_type not in ('teacher', 'admin'):
        messages.error(request, "Sizga ruxsat yo'q!")
        return redirect('users:dashboard')

    exam = get_object_or_404(Exam, id=exam_id, created_by=user)
    title = exam.title
    exam.delete()
    messages.success(request, f"'{title}' testi o'chirildi!")
    return redirect('exams:teacher_my_tests')


# ===== ADMIN O'QITUVCHI BOSHQARUVI =====

@login_required
def admin_teachers(request):
    """Admin sahifasi — o'qituvchilarni boshqarish"""
    user = request.user
    if user.user_type != 'admin' and not user.is_superuser:
        messages.error(request, "Faqat administratorlar uchun!")
        return redirect('users:dashboard')

    teachers = CustomUser.objects.filter(user_type='teacher').order_by('first_name', 'last_name')

    # Har bir o'qituvchi uchun statistika
    from apps.exams.models import ExamAssignment, ExamGroupPermission
    teacher_stats = []
    for teacher in teachers:
        assignments_count = ExamAssignment.objects.filter(teacher=teacher).count()
        permissions_count = ExamGroupPermission.objects.filter(teacher=teacher, is_active=True).count()
        teacher_stats.append({
            'teacher': teacher,
            'assignments_count': assignments_count,
            'permissions_count': permissions_count,
        })

    context = {
        'teacher_stats': teacher_stats,
        'total_teachers': teachers.count(),
    }
    return render(request, 'exams/admin_teachers.html', context)


@login_required
def admin_create_teacher(request):
    """Admin — yangi o'qituvchi yaratish"""
    user = request.user
    if user.user_type != 'admin' and not user.is_superuser:
        messages.error(request, "Faqat administratorlar uchun!")
        return redirect('users:dashboard')

    if request.method != 'POST':
        return redirect('exams:admin_teachers')

    username = request.POST.get('username', '').strip()
    first_name = request.POST.get('first_name', '').strip()
    last_name = request.POST.get('last_name', '').strip()
    email = request.POST.get('email', '').strip()
    phone = request.POST.get('phone', '').strip()
    password = request.POST.get('password', '').strip()
    password2 = request.POST.get('password2', '').strip()

    # Validatsiya
    if not username or not first_name or not last_name or not password:
        messages.error(request, "Ism, familiya, username va parol kiritilishi shart!")
        return redirect('exams:admin_teachers')

    if password != password2:
        messages.error(request, "Parollar mos emas!")
        return redirect('exams:admin_teachers')

    if CustomUser.objects.filter(username=username).exists():
        messages.error(request, f"'{username}' username allaqachon band!")
        return redirect('exams:admin_teachers')

    if email and CustomUser.objects.filter(email=email).exists():
        messages.error(request, f"'{email}' email allaqachon ro'yxatdan o'tgan!")
        return redirect('exams:admin_teachers')

    teacher = CustomUser.objects.create_user(
        username=username,
        password=password,
        first_name=first_name,
        last_name=last_name,
        email=email,
        phone=phone or None,
        user_type='teacher',
    )

    messages.success(request, f"O'qituvchi '{teacher.get_full_name()}' muvaffaqiyatli qo'shildi!")
    return redirect('exams:admin_teachers')


@login_required
def admin_edit_teacher(request, teacher_id):
    """Admin — o'qituvchi ma'lumotlarini tahrirlash"""
    user = request.user
    if user.user_type != 'admin' and not user.is_superuser:
        messages.error(request, "Faqat administratorlar uchun!")
        return redirect('users:dashboard')

    teacher = get_object_or_404(CustomUser, id=teacher_id, user_type='teacher')

    if request.method != 'POST':
        return redirect('exams:admin_teachers')

    first_name = request.POST.get('first_name', '').strip()
    last_name = request.POST.get('last_name', '').strip()
    email = request.POST.get('email', '').strip()
    phone = request.POST.get('phone', '').strip()
    new_password = request.POST.get('new_password', '').strip()

    if not first_name or not last_name:
        messages.error(request, "Ism va familiya kiritilishi shart!")
        return redirect('exams:admin_teachers')

    if email and CustomUser.objects.filter(email=email).exclude(id=teacher.id).exists():
        messages.error(request, f"'{email}' email boshqa foydalanuvchida mavjud!")
        return redirect('exams:admin_teachers')

    teacher.first_name = first_name
    teacher.last_name = last_name
    teacher.email = email
    teacher.phone = phone or None

    if new_password:
        teacher.set_password(new_password)

    teacher.save()

    messages.success(request, f"O'qituvchi '{teacher.get_full_name()}' ma'lumotlari yangilandi!")
    return redirect('exams:admin_teachers')


@login_required
def admin_delete_teacher(request, teacher_id):
    """Admin — o'qituvchini o'chirish"""
    user = request.user
    if user.user_type != 'admin' and not user.is_superuser:
        messages.error(request, "Faqat administratorlar uchun!")
        return redirect('users:dashboard')

    teacher = get_object_or_404(CustomUser, id=teacher_id, user_type='teacher')
    full_name = teacher.get_full_name()

    # O'qituvchining tayinlanishlarini tekshirish
    active_assignments = ExamAssignment.objects.filter(teacher=teacher).count()
    if active_assignments > 0:
        # Tayinlanishlarni ham o'chiramiz
        ExamAssignment.objects.filter(teacher=teacher).delete()
        ExamGroupPermission.objects.filter(teacher=teacher).delete()

    teacher.delete()
    messages.success(request, f"O'qituvchi '{full_name}' tizimdan o'chirildi!")
    return redirect('exams:admin_teachers')


# ===== ADMIN RUXSAT BERISH VIEWS =====

@login_required
def admin_assignments(request):
    """Admin sahifasi — imtihonlarni o'qituvchilarga tayinlash"""
    user = request.user
    if user.user_type != 'admin' and not user.is_superuser:
        messages.error(request, "Faqat administratorlar uchun!")
        return redirect('users:dashboard')

    now = timezone.now()

    # Fanlar bo'yicha o'qituvchilar va ularning tayinlanishlari
    subjects = Subject.objects.all()
    teachers = CustomUser.objects.filter(user_type='teacher').order_by('first_name', 'last_name')
    exams = Exam.objects.filter(is_active=True).select_related('subject').order_by('subject__name', 'title')

    # Mavjud tayinlanishlar
    assignments = ExamAssignment.objects.select_related(
        'exam', 'exam__subject', 'teacher', 'assigned_by'
    ).order_by('exam__subject__name', 'teacher__first_name')

    # Filtrlash
    selected_subject = request.GET.get('subject', '')
    if selected_subject:
        assignments = assignments.filter(exam__subject_id=selected_subject)
        exams = exams.filter(subject_id=selected_subject)

    context = {
        'subjects': subjects,
        'teachers': teachers,
        'exams': exams,
        'assignments': assignments,
        'now': now,
        'selected_subject': selected_subject,
    }
    return render(request, 'exams/admin_assignments.html', context)


@login_required
def admin_create_assignment(request):
    """Admin — yangi tayinlanish yaratish"""
    user = request.user
    if user.user_type != 'admin' and not user.is_superuser:
        messages.error(request, "Faqat administratorlar uchun!")
        return redirect('users:dashboard')

    if request.method != 'POST':
        return redirect('exams:admin_assignments')

    exam_id = request.POST.get('exam_id')
    teacher_id = request.POST.get('teacher_id')
    start_time_str = request.POST.get('start_time', '').strip()
    deadline_str = request.POST.get('deadline', '').strip()

    if not exam_id or not teacher_id or not deadline_str:
        messages.error(request, "Imtihon, o'qituvchi va tugash vaqti tanlanishi shart!")
        return redirect('exams:admin_assignments')

    exam = get_object_or_404(Exam, id=exam_id)
    teacher = get_object_or_404(CustomUser, id=teacher_id, user_type='teacher')

    from datetime import datetime
    try:
        admin_deadline = timezone.make_aware(datetime.strptime(deadline_str, '%Y-%m-%dT%H:%M'))
    except (ValueError, TypeError):
        messages.error(request, "Tugash vaqti formati noto'g'ri!")
        return redirect('exams:admin_assignments')

    admin_start_time = None
    if start_time_str:
        try:
            admin_start_time = timezone.make_aware(datetime.strptime(start_time_str, '%Y-%m-%dT%H:%M'))
        except (ValueError, TypeError):
            messages.error(request, "Boshlanish vaqti formati noto'g'ri!")
            return redirect('exams:admin_assignments')

    if admin_start_time and admin_start_time >= admin_deadline:
        messages.error(request, "Boshlanish vaqti tugash vaqtidan oldin bo'lishi kerak!")
        return redirect('exams:admin_assignments')

    # Yaratish yoki yangilash
    assignment, created = ExamAssignment.objects.update_or_create(
        exam=exam,
        teacher=teacher,
        defaults={
            'admin_start_time': admin_start_time,
            'admin_deadline': admin_deadline,
            'assigned_by': user,
        }
    )

    # O'qituvchiga bildirishnoma yuborish
    start_info = ''
    if admin_start_time:
        start_info = f"Boshlanish: {admin_start_time.strftime('%d.%m.%Y %H:%M')}\n"

    Notification.objects.create(
        user=teacher,
        notification_type='assignment',
        title=f"Yangi imtihon tayinlandi: {exam.title}",
        message=(
            f"Sizga \"{exam.title}\" ({exam.subject.name}) imtihoni tayinlandi.\n"
            f"{start_info}"
            f"Tugash muddati: {admin_deadline.strftime('%d.%m.%Y %H:%M')}\n"
            f"Tayinlagan: {user.get_full_name()}\n\n"
            f"O'qituvchi boshqaruv panelidan guruhlarni tanlashingiz va ruxsat berishingiz mumkin."
        )
    )

    action = "tayinlandi" if created else "yangilandi"
    messages.success(
        request,
        f"'{exam.title}' imtihoni {teacher.get_full_name()} ga {action}! "
        f"O'qituvchiga bildirishnoma yuborildi."
    )
    return redirect('exams:admin_assignments')


@login_required
def admin_delete_assignment(request, assignment_id):
    """Admin — tayinlanishni o'chirish"""
    user = request.user
    if user.user_type != 'admin' and not user.is_superuser:
        messages.error(request, "Faqat administratorlar uchun!")
        return redirect('users:dashboard')

    assignment = get_object_or_404(ExamAssignment, id=assignment_id)
    teacher = assignment.teacher
    exam_title = assignment.exam.title

    # O'qituvchiga bildirishnoma
    Notification.objects.create(
        user=teacher,
        notification_type='info',
        title=f"Imtihon tayinlanishi bekor qilindi",
        message=(
            f"\"{exam_title}\" imtihoni uchun tayinlanishingiz "
            f"administrator ({user.get_full_name()}) tomonidan bekor qilindi."
        )
    )

    assignment.delete()
    messages.success(request, f"'{exam_title}' tayinlanishi o'chirildi. O'qituvchiga xabar yuborildi.")
    return redirect('exams:admin_assignments')


# ===== BILDIRISHNOMALAR =====

@login_required
def notifications(request):
    """Foydalanuvchi bildirishnomalari"""
    user_notifications = request.user.notifications.all()[:50]
    unread_count = request.user.notifications.filter(is_read=False).count()

    context = {
        'notifications': user_notifications,
        'unread_count': unread_count,
    }
    return render(request, 'users/notifications.html', context)


@login_required
def mark_notification_read(request, notification_id):
    """Bildirishnomani o'qilgan deb belgilash"""
    notification = get_object_or_404(
        Notification, id=notification_id, user=request.user
    )
    notification.is_read = True
    notification.save()
    return redirect('users:notifications')


@login_required
def mark_all_notifications_read(request):
    """Barcha bildirishnomalarni o'qilgan deb belgilash"""
    request.user.notifications.filter(is_read=False).update(is_read=True)
    messages.success(request, "Barcha bildirishnomalar o'qilgan deb belgilandi.")
    return redirect('users:notifications')


@login_required
def admin_subjects(request):
    """Admin — fanlarni boshqarish (ro'yxat, qidiruv)"""
    user = request.user
    if user.user_type != 'admin' and not user.is_superuser:
        messages.error(request, "Faqat administratorlar uchun!")
        return redirect('users:dashboard')

    search_q = request.GET.get('q', '').strip()
    subjects = Subject.objects.all().order_by('name')
    if search_q:
        subjects = subjects.filter(name__icontains=search_q)

    context = {
        'subjects': subjects,
        'search_q': search_q,
    }
    return render(request, 'exams/admin_subjects.html', context)


@login_required
def admin_create_subject(request):
    """Admin — yangi fan yaratish"""
    user = request.user
    if user.user_type != 'admin' and not user.is_superuser:
        messages.error(request, "Faqat administratorlar uchun!")
        return redirect('users:dashboard')

    if request.method != 'POST':
        return redirect('exams:admin_subjects')

    name = request.POST.get('name', '').strip()
    description = request.POST.get('description', '').strip()

    if not name:
        messages.error(request, "Fan nomi kiritilishi shart!")
        return redirect('exams:admin_subjects')

    if Subject.objects.filter(name__iexact=name).exists():
        messages.error(request, f"'{name}' nomli fan allaqachon mavjud!")
        return redirect('exams:admin_subjects')

    Subject.objects.create(name=name, description=description)
    messages.success(request, f"'{name}' fan yaratildi!")
    return redirect('exams:admin_subjects')


@login_required
def admin_edit_subject(request, subject_id):
    """Admin — fanni tahrirlash"""
    user = request.user
    if user.user_type != 'admin' and not user.is_superuser:
        messages.error(request, "Faqat administratorlar uchun!")
        return redirect('users:dashboard')

    subject = get_object_or_404(Subject, id=subject_id)

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        if not name:
            messages.error(request, "Fan nomi kiritilishi shart!")
            return redirect('exams:admin_subjects')
        if Subject.objects.filter(name__iexact=name).exclude(id=subject.id).exists():
            messages.error(request, f"'{name}' nomli fan allaqachon mavjud!")
            return redirect('exams:admin_subjects')
        subject.name = name
        subject.description = description
        subject.save()
        messages.success(request, "Fan ma'lumotlari yangilandi.")
        return redirect('exams:admin_subjects')

    # GET — show edit form is handled in the list template via modal
    return redirect('exams:admin_subjects')


@login_required
def admin_delete_subject(request, subject_id):
    """Admin — fanni o'chirish (agar unga bog'langan imtihonlar bo'lmasa)"""
    user = request.user
    if user.user_type != 'admin' and not user.is_superuser:
        messages.error(request, "Faqat administratorlar uchun!")
        return redirect('users:dashboard')

    subject = get_object_or_404(Subject, id=subject_id)
    linked_exams = subject.exams.count()
    if linked_exams > 0:
        messages.error(request, f"'{subject.name}' faniga {linked_exams} ta imtihon bog'langan. Avval imtihonlarni o'chiring.")
        return redirect('exams:admin_subjects')

    name = subject.name
    subject.delete()
    messages.success(request, f"'{name}' fan o'chirildi.")
    return redirect('exams:admin_subjects')


# ===== ADMIN O'QUVCHILAR BOSHQARUVI =====

@login_required
def admin_students(request):
    """Admin — O'quvchilarni boshqarish va guruhga biriktirish"""
    user = request.user
    if user.user_type != 'admin' and not user.is_superuser:
        messages.error(request, "Faqat administratorlar uchun!")
        return redirect('users:dashboard')

    # Filtrlash
    filter_group = request.GET.get('group', '')
    filter_status = request.GET.get('status', '')
    search_q = request.GET.get('q', '').strip()

    students = CustomUser.objects.filter(user_type='student').select_related('student_group').order_by('last_name', 'first_name')

    if filter_group == 'none':
        students = students.filter(student_group__isnull=True)
    elif filter_group:
        students = students.filter(student_group_id=filter_group)

    if search_q:
        students = students.filter(
            models.Q(first_name__icontains=search_q) |
            models.Q(last_name__icontains=search_q) |
            models.Q(username__icontains=search_q)
        )

    groups = StudentGroup.objects.all().order_by('name')

    # O'quvchilarni guruhga biriktirish uchun POST
    no_group_count = CustomUser.objects.filter(user_type='student', student_group__isnull=True).count()
    total_students = CustomUser.objects.filter(user_type='student').count()

    context = {
        'students': students,
        'groups': groups,
        'filter_group': filter_group,
        'filter_status': filter_status,
        'search_q': search_q,
        'no_group_count': no_group_count,
        'total_students': total_students,
    }
    return render(request, 'exams/admin_students.html', context)


@login_required
def admin_assign_student_group(request):
    """Admin — o'quvchini guruhga biriktirish"""
    user = request.user
    if user.user_type != 'admin' and not user.is_superuser:
        messages.error(request, "Faqat administratorlar uchun!")
        return redirect('users:dashboard')

    if request.method != 'POST':
        return redirect('exams:admin_students')

    student_id = request.POST.get('student_id')
    group_id = request.POST.get('group_id', '').strip()

    student = get_object_or_404(CustomUser, id=student_id, user_type='student')

    if group_id == '' or group_id == 'none':
        old_group = student.student_group
        student.student_group = None
        student.save()
        if old_group:
            messages.success(request, f"{student.get_full_name()} '{old_group.name}' guruhidan chiqarildi.")

            # Bildirishnoma
            Notification.objects.create(
                user=student,
                notification_type='info',
                title="Guruhdan chiqarildingiz",
                message=f"Siz '{old_group.name}' guruhidan administrator tomonidan chiqarildingiz."
            )
        else:
            messages.info(request, f"{student.get_full_name()} allaqachon hech qaysi guruhda emas.")
    else:
        group = get_object_or_404(StudentGroup, id=group_id)
        old_group = student.student_group
        student.student_group = group
        student.save()

        action = "o'zgartirildi" if old_group else "biriktirildi"
        messages.success(request, f"{student.get_full_name()} '{group.name}' guruhiga {action}!")

        # Bildirishnoma
        msg = f"Siz '{group.name}' guruhiga biriktirildigiz."
        if old_group:
            msg = f"Sizning guruhingiz '{old_group.name}' dan '{group.name}' ga o'zgartirildi."
        Notification.objects.create(
            user=student,
            notification_type='assignment',
            title=f"Guruhga biriktirildi: {group.name}",
            message=msg
        )

    return redirect('exams:admin_students')


@login_required
def admin_create_group(request):
    """Admin — yangi guruh yaratish"""
    user = request.user
    if user.user_type != 'admin' and not user.is_superuser:
        messages.error(request, "Faqat administratorlar uchun!")
        return redirect('users:dashboard')

    if request.method != 'POST':
        return redirect('exams:admin_students')

    name = request.POST.get('name', '').strip()
    description = request.POST.get('description', '').strip()

    if not name:
        messages.error(request, "Guruh nomi kiritilishi shart!")
        return redirect('exams:admin_students')

    if StudentGroup.objects.filter(name=name).exists():
        messages.error(request, f"'{name}' nomli guruh allaqachon mavjud!")
        return redirect('exams:admin_students')

    StudentGroup.objects.create(name=name, description=description)
    messages.success(request, f"'{name}' guruhi yaratildi!")
    return redirect('exams:admin_students')


@login_required
def admin_delete_group(request, group_id):
    """Admin — guruhni o'chirish"""
    user = request.user
    if user.user_type != 'admin' and not user.is_superuser:
        messages.error(request, "Faqat administratorlar uchun!")
        return redirect('users:dashboard')

    group = get_object_or_404(StudentGroup, id=group_id)
    student_count = group.students.count()

    if student_count > 0:
        messages.error(request, f"'{group.name}' guruhida {student_count} ta o'quvchi bor. Avval o'quvchilarni boshqa guruhga o'tkazing!")
        return redirect('exams:admin_students')

    name = group.name
    group.delete()
    messages.success(request, f"'{name}' guruhi o'chirildi!")
    return redirect('exams:admin_students')
