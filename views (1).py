from audioop import reverse
from django.shortcuts import get_object_or_404, render, redirect
from django.http import Http404, HttpResponse, FileResponse
from institute.models import Announcements, Student
from students.models import ExtendOuting, Outing, Vacation, Attendance
from complaints.models import Complaint
from django.contrib.messages.views import SuccessMessageMixin
from django.contrib.auth.decorators import user_passes_test
from django.views.generic import CreateView, ListView
from django.contrib.auth.mixins import UserPassesTestMixin
from django.urls import reverse_lazy
from .forms import OutingExtendForm, OutingForm
from django.db.models import F
from django.contrib import messages
from django.utils import timezone
import io
from vacation_form import create_vacation_form
from hosteldb.settings import LOGIN_URL



class StudentTestMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.is_student

class RoomAllotmentTestMixin(UserPassesTestMixin):
    def test_func(self):
        if self.request.user.is_student and self.request.user.student.roomdetail and self.request.user.student.roomdetail.room()!='-':
            return True
        return False

def student_check(user):
    return user.is_authenticated and user.is_student

def room_allotment_check(user):
    return user.is_authenticated and user.is_student and user.student.roomdetail and user.student.roomdetail.room()!='-'

# Create your views here.

@user_passes_test(student_check)
def home(request):
    user = request.user
    student = user.student
    present_dates_count = 0
    absent_dates_count = 0
    if user.student.roomdetail and user.student.roomdetail.room()=='-':
        raise Http404('You are not allocated any room yet')
    if Attendance.objects.filter(student=student).exists():
        present_dates_count = (student.attendance and student.attendance.present_dates and len(student.attendance.present_dates.split(','))) or 0
        absent_dates_count = (student.attendance and student.attendance.absent_dates and len(student.attendance.absent_dates.split(','))) or 0
    outing_count = 0
    for outing in student.outing_set.all():
        if outing.is_upcoming():
            outing_count+=1
    outing_rating = student.outing_rating
    discipline_rating = student.discipline_rating
    complaints = Complaint.objects.filter(user = user)
    announce_obj = student.related_announcements()[:5]
    return render(request, 'students/home.html', {'student': student, 'present_dates_count':present_dates_count, \
        'absent_dates_count':absent_dates_count, 'outing_count': outing_count, 'complaints':complaints, 'outing_rating':outing_rating, \
            'announce_obj':announce_obj, 'discipline_rating':discipline_rating})


class OutingListView(StudentTestMixin, ListView):
    model = Student
    template_name = 'students/outing_list.html'
    context_object_name = 'outing_list'

    def get_queryset(self):
        outing_set = Outing.objects.filter(student=self.request.user.student).annotate(outTime=F('outinginouttimes__outTime'), \
            inTime=F('outinginouttimes__inTime'))
        return outing_set


class OutingCreateView(StudentTestMixin, SuccessMessageMixin, CreateView):
    model = Outing
    form_class = OutingForm
    template_name = 'students/outing_form.html'
    success_url = reverse_lazy('students:outing_list')
    success_message = 'Outing application successfully created!'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form_title'] = 'Outing Application'
        return context
    def get_form_kwargs(self):
        kwargs = super(OutingCreateView, self).get_form_kwargs()
        kwargs['request'] = self.request
        return kwargs
    def form_valid(self, form):
        form.instance.student = self.request.user.student
        return super().form_valid(form)

# class OutingUpdateView(StudentTestMixin, SuccessMessageMixin, UpdateView):
#     model = Outing
#     form_class = OutingForm
#     template_name = 'students/outing_form.html'
#     success_url = reverse_lazy('students:outing_list')
#     success_message = 'Outing application successfully updated!'

#     def get(self, request, *args, **kwargs):
#         response =  super().get(request, *args, **kwargs)
#         if not (self.object.student == self.request.user.student and self.object.is_editable()): 
#             raise Http404('Cannot edit the outing application.')
#         return response

#     def get_context_data(self, **kwargs):
#         context = super().get_context_data(**kwargs)
#         if self.object.is_editable():
#             context['form_title'] = 'Edit Outing Application'
#         return context
    
#     def get_form_kwargs(self):
#         kwargs = super(OutingUpdateView, self).get_form_kwargs()
#         kwargs['request'] = self.request
#         return kwargs

#     def form_valid(self, form):
#         form.instance.student = self.request.user.student
#         return super().form_valid(form)


@user_passes_test(student_check)
def attendance_history(request):
    student = request.user.student
    present_dates = (student.attendance.present_dates and student.attendance.present_dates.split(',')) or None
    absent_dates = (student.attendance.absent_dates and student.attendance.absent_dates.split(',')) or None
    if absent_dates:
        absent_dates = [absent_date.split('@')[0] for absent_date in absent_dates]
    if present_dates:
        present_dates = [present_date.split('@')[0] for present_date in present_dates]

    return render(request, 'students/attendance_history.html', {'student': student, 'present_dates': present_dates, 'absent_dates': absent_dates})

@user_passes_test(student_check)
def cancel_outing(request, pk):
    if request.method == 'POST':
        outing = get_object_or_404(Outing, id=pk)
        if outing.can_cancel():
            if outing.permission == 'Pending':
                Outing.objects.get(id=pk).delete()
            elif outing.status!='In Outing':
                outing.permission = 'Revoked'
                outing.save()
        return redirect('students:outing_list')
    else:
        return HttpResponse("not post")

@user_passes_test(student_check)
def outing_QRCode(request, pk):
    outing_obj = get_object_or_404(Outing, id=pk)
    if outing_obj.is_qr_viewable():
        return render(request, 'students/render_qr_code.html', {'outing':outing_obj})
    messages.error(request, 'Qr is not viewable yet.')
    return redirect('students:home')


@user_passes_test(student_check)
def outing_details(request, pk):
    outing_set = Outing.objects.filter(id=pk).annotate(outTime=F('outinginouttimes__outTime'), \
            inTime=F('outinginouttimes__inTime'), remark_by_security=F('outinginouttimes__remark_by_security'))
    return render(request, 'students/outing_specific.html', {'outing':outing_set[0]})
class OutingExtendView(StudentTestMixin, SuccessMessageMixin, CreateView):
    model = ExtendOuting
    form_class = OutingExtendForm
    template_name = 'students/outing_form.html'
    success_url = reverse_lazy('students:outing_list')
    success_message = 'Outing application successfully extended!'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form_title'] = 'Extend Outing Application'
        return context
    def get_form_kwargs(self):
        kwargs = super(OutingExtendView, self).get_form_kwargs()
        outing = get_object_or_404(Outing, id=self.kwargs['pk'])
        kwargs['object'] = outing
        kwargs['request'] = self.request
        return kwargs
    def form_valid(self, form):
        outing = get_object_or_404(Outing, id=self.kwargs['pk'])
        outing.permission = 'Pending Extension'
        outing.save()
        form.instance.outing = outing
        return super().form_valid(form)

@user_passes_test(student_check)
def vacation_history(request):
    user = request.user
    student = user.student
    if not Vacation.objects.filter(room_detail=student.roomdetail).exists():
        messages.error(request, 'No vacation history found.')
        return redirect('students:home')
    else:
        vac = get_object_or_404(Vacation, room_detail=student.roomdetail)
        return render(request, 'students/vacation_history.html', {'vac':vac})



@user_passes_test(student_check)
def vacation_form_download(request):
    user = request.user
    student = user.student

    vac = get_object_or_404(Vacation, room_detail=student.roomdetail)

    buf = io.BytesIO()

    context = {'vac':vac}

    create_vacation_form(buf, context)

    buf.seek(0)
    file = 'Vacation_form-{}/{}.{}'.format(vac.room_detail.__str__(), timezone.localtime().strftime('%d-%m-%Y_%H-%M-%S'),'pdf')
    return FileResponse(buf, as_attachment=True, filename=file)

def send_birthday_mail():
    # search the query set for birthday and send him email
    from datetime import datetime
    query_set=Student.objects.all()
    bday_fellows=query_set.filter(dob=datetime.today().date())

    from django.core.mail import send_mail
    from django.conf import settings
    for student in bday_fellows:
        from django.core.mail import EmailMultiAlternatives
        from django.template.loader import get_template
        from django.template import Context

        subject, from_email, to = 'Happy Birthday',settings.EMAIL_HOST_USER, student.user.email

        variables = {
        'student':student
        }
        html_content = get_template('students/birthyday_mail_template_html.html').render(variables)
        text_content = get_template('students/birthyday_mail_template_text.html').render(variables)
        msg = EmailMultiAlternatives(subject, text_content, from_email, [to])
        msg.attach_alternative(html_content, "text/html")
        msg.send()
