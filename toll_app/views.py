import uuid
from .ANPRS_2.detect import generate_frames_sort, process_image, get_realtime_plates, clear_realtime_plates, stop_live_detection
from toll_app.forms import SignupForm, LoginForm, ManualEntryForm, forms
from django.http import StreamingHttpResponse, JsonResponse
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from .models import UserDetails, Transactions
from .enums import VehicleRate, VehicleType
from django.views.decorators import gzip
from django.contrib import messages
from django.db import models, transaction as db_transaction
from decimal import Decimal
import datetime


live_plate_db_flag = {}

def index(request):
    return render(request, 'toll_app/index.html')


def login_view(request):
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']
            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                if UserDetails.objects.filter(id=user.id).first().is_superuser:
                    return redirect('admin_dashboard')
                else:
                    return redirect('dashboard')
            else:
                form.add_error(None, 'Invalid username or password')
    else:
        form = LoginForm()
    return render(request, 'toll_app/login.html', {'form': form})


def signup(request):
    if request.method == 'POST':
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('dashboard')
    else:
        form = SignupForm()
    return render(request, 'toll_app/signup.html', {'form': form})


@login_required
def logout_view(request):
    logout(request)
    return redirect('index')


@login_required
def dashboard(request):
    if request.user.is_superuser:
        return redirect('admin_dashboard')
    txn = Transactions.objects.filter(user=request.user).order_by('-timestamp')[:10]
    return render(request, 'toll_app/user.html', {'user': request.user, 'transactions': txn})


@login_required
def recharge_account(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    try:
        amount = request.GET.get('amount', '0')
        amount = Decimal(amount)
        if amount <= 0:
            return JsonResponse({'error': 'Invalid amount'}, status=400)

        user = UserDetails.objects.get(id=request.user.id)
        user.balance += amount
        user.save()

        return JsonResponse({'success': True, 'new_balance': float(user.balance)})
    except ValueError:
        return JsonResponse({'error': 'Amount must be a number'}, status=400)
    except UserDetails.DoesNotExist:
        return JsonResponse({'error': 'User not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def admin_dashboard(request):
    if not request.user.is_superuser:
        return redirect('dashboard')

    txn = Transactions.objects.all()

    vehicle_passed_total = {
        'bike': txn.filter(vehicle_type=VehicleType.BIKE.value).count(),
        'car': txn.filter(vehicle_type=VehicleType.CAR.value).count(),
        'large': txn.filter(vehicle_type=VehicleType.LARGE.value).count(),
        'total': txn.count()
    }

    total_revenue = {
        'bike': txn.filter(vehicle_type=VehicleType.BIKE.value).aggregate(models.Sum('fee'))['fee__sum'] or 0,
        'car': txn.filter(vehicle_type=VehicleType.CAR.value).aggregate(models.Sum('fee'))['fee__sum'] or 0,
        'large': txn.filter(vehicle_type=VehicleType.LARGE.value).aggregate(models.Sum('fee'))['fee__sum'] or 0,
        'total': txn.aggregate(models.Sum('fee'))['fee__sum'] or 0
    }

    recent_transactions = txn.order_by('-timestamp')[:10]

    user_list = UserDetails.objects.filter(is_superuser=False).all()
    active_today = user_list.filter(
        last_login__date=datetime.date.today()
    ).count()

    context = {
        'user_list': user_list,
        'active_today': active_today,
        'vehicle_passed': vehicle_passed_total,
        'revenue': total_revenue,
        'recent_transactions': recent_transactions,
        'vehicle_types': [('all', 'All Vehicles')] + [(vt.value, vt.name) for vt in VehicleType]
    }

    return render(request, 'toll_app/admin.html', context)


@login_required
def history(request):
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    user_id = request.GET.get('user_id', 'all')
    vehicle_type = request.GET.get('vehicle_type', 'all')
    days = int(request.GET.get('days', 7))

    end_date = datetime.date.today()
    start_date = end_date - datetime.timedelta(days=days)

    txn = Transactions.objects.filter(timestamp__date__range=[start_date, end_date]).all()

    if user_id and user_id != 'all':
        txn = txn.filter(user__id=user_id).all()

    if vehicle_type and vehicle_type != 'all':
        txn = txn.filter(vehicle_type=vehicle_type).all()

    history_data = []
    for transaction in txn.order_by('-timestamp'):
        history_data.append({
            'id': str(transaction.id),
            'user': f"{transaction.user.first_name} {transaction.user.last_name}",
            'vehicle_type': transaction.vehicle_type,
            'vehicle_number': transaction.user.vehicle_number,
            'fee': float(transaction.fee),
            'remaining_balance': float(transaction.remaining_balance),
            'timestamp': transaction.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'image_path': transaction.image_path
        })

    return JsonResponse({
        'history': history_data,
        'count': len(history_data),
        'period': f"{start_date} to {end_date}"
    })


@login_required
def manual_entry(request):
    if not request.user.is_superuser:
        messages.error(request, 'Unauthorized access')
        return redirect('dashboard')

    if request.method == 'POST':
        form = ManualEntryForm(request.POST, request=request)
        if form.is_valid():
            try:
                transaction = form.save()
                messages.success(
                    request,
                    f"Transaction recorded successfully. NRP {transaction.fee} deducted from {transaction.user.first_name}'s account. New balance: NRP {transaction.user.balance}"
                )
                return JsonResponse({
                    'success': True,
                    'message': f'Transaction recorded successfully. NRP {transaction.fee} deducted',
                    'transaction_id': str(transaction.id)
                })
            except Exception as e:
                messages.error(request, str(e))
                return JsonResponse({
                    'success': False,
                    'error': str(e)
                }, status=400)
        else:
            errors = form.errors.as_json()
            return JsonResponse({
                'success': False,
                'error': 'Invalid form data',
                'errors': errors
            }, status=400)

    else:
        form = ManualEntryForm(request=request)

    rate_info = {
        'bike_rate': VehicleRate.BIKE.value,
        'car_rate': VehicleRate.CAR.value,
        'large_rate': VehicleRate.LARGE.value
    }

    return render(request, 'toll_app/manual_entry.html', {
        'form': form,
        'rate_info': rate_info,
        'user_list': UserDetails.objects.filter(is_superuser=False)
    })


@login_required
def process_video(request):
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    if request.method == 'POST' and request.FILES.get('video'):
        try:
            video_file = request.FILES['video']

            results = process_video_sort(video_file)

            return JsonResponse({
                'success': True,
                'results': results,
                'message': 'Video processing completed successfully'
            })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'Error processing video: {str(e)}'
            }, status=500)

    return JsonResponse({'error': 'No video file provided'}, status=400)

@login_required
def live_detect(request):
    return render(request, 'toll_app/auto.html')


@login_required
def video_feed(request):
    try:
        return StreamingHttpResponse(
            generate_frames_sort(),
            content_type='multipart/x-mixed-replace; boundary=frame'
        )
    except Exception as e:
        print(f"Error in video_feed: {e}")
        return JsonResponse({'error': 'Cannot start video stream'}, status=500)

@login_required
def get_detected_plates(request):
    try:
        plates = get_realtime_plates()

        # for plate in plates:
        #     if plate['text'] not in live_plate_db_flag:
        #         if save_transactions(plate):
        #             live_plate_db_flag[plate['text']] = datetime.datetime.now()
        #     else:
        #         if (datetime.datetime.now() - live_plate_db_flag[plate['text']]).seconds > 60:
        #             if save_transactions(plate):
        #                 live_plate_db_flag[plate['text']] = datetime.datetime.now()
        return JsonResponse({'plates': plates, 'success': True})
    except Exception as e:
        return JsonResponse({'error': str(e), 'success': False}, status=500)

@login_required
def process_single_frame(request):
    if request.method == 'POST' and request.FILES.get('image'):
        try:
            image_file = request.FILES['image']
            result = process_image(image_file)
            return JsonResponse({
                'success': True,
                'results': results,
                'error': 'Successfully processed image'
            }, status=200)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'Error processing image: {str(e)}'
            }, status=500)
    return JsonResponse({
        'success': False,
        'error': f'Error processing image'
    }, status=500)

@login_required
def start_detection(request):
    try:
        clear_realtime_plates()
        return JsonResponse({'success': True, 'message': 'Detection started'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
def stop_detection(request):
    try:
        clear_realtime_plates()
        stop_live_detection()
        return JsonResponse({'success': True, 'message': 'Detection stopped'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
def ws_live_detect(request):
    return render(request, 'toll_app/ws.html')


