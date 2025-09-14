from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from toll_app.forms import SignupForm, LoginForm, ManualEntryForm, forms
from .enums import VehicleRate



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
                # if user.is_authenticated():
                #     return redirect('admin_dashboard')
                # else:
                #     return redirect('user_dashboard')
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
            # if user.is_authenticated():
            #     return redirect('admin_dashboard')
            # else:
            #     return redirect('user_dashboard')
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
    return render(request, 'toll_app/user.html', {'user': request.user})


@login_required
def admin_dashboard(request):
    pass


@login_required
def history(request):
    user_id = request.GET.get('user_id', None)  # Default empty string
    vehicle_type = request.GET.get('vehicle_type', None)  # Default None
    before = request.GET.get('before', None)  # Default to page 1
    sort = request.GET.get('sort', 'name')  # Default sort by name
    pass


@login_required
def manual_entry(request):
    if request.method == 'POST':
        form = ManualEntryForm(request.POST, request=request)
        print(type(request.POST.get('timestamp')))
        if form.is_valid():
            try:
                transaction = form.save()
                messages.success(
                    request,
                    f"Transaction recorded successfully. ₹{transaction.fee} deducted from {transaction.user.first_name}'s account. New balance: ₹{transaction.user.balance}"
                )
                return redirect('dashboard')
            except forms.ValidationError as e:
                messages.error(request, str(e))
    else:
        form = ManualEntryForm(request=request)

    # Pass rate information to template
    rate_info = {
        'bike_rate': VehicleRate.BIKE.value,
        'car_rate': VehicleRate.CAR.value,
        'large_rate': VehicleRate.LARGE.value
    }

    return render(request, 'toll_app/manual.html', {'form': form, 'rate_info': rate_info})


def live_detect(request):
    pass



