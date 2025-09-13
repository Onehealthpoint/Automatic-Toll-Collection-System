from django.shortcuts import render

@require_http_methods(["GET"])
def index(request):
    return render(request, 'index.html')

@require_http_methods(["GET", "POST"])
def login(request):
    if request.method == 'GET':
        return render(request, 'login.html')

    elif request.method == 'POST':
        username = request.POST.get('username')
        firstname = request.POST.get('firstname')
        lastname = request.POST.get('lastname')
        email = request.POST.get('email')
        phone = request.POST.get('phone')
        vehicle_plate = request.POST.get('vehicle_plate')
        vehicle_type = request.POST.get('vehicle_type')
        password = request.POST.get('password')
        # user = authenticate(request, username=username, password=password)

        if user is not None:
            auth_login(request, user)
            return redirect('index')
        else:
            return render(request, 'login.html', {'error': 'Invalid credentials'})
    return render(request, 'error.html')


@require_http_methods(["GET", "POST"])
def login(request):
    if request.method == 'GET':
        return render(request, 'signup.html')

    elif request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        # user = authenticate(request, username=username, password=password)

        if user is not None:
            auth_login(request, user)
            return redirect('index')
        else:
            return render(request, 'signup.html', {'error': 'Invalid credentials'})
    return render(request, 'error.html')


@require_http_methods(["GET"])
def user_dashboard(request, user_id):
    pass

@require_http_methods(["GET"])
def admin_dashboard(request):
    pass

@require_http_methods(["GET"])
def user_history(request, user_id):

    pass

@require_http_methods(["GET"])
def history(request):
    user_id = request.GET.get('user_id', None)  # Default empty string
    vehicle_type = request.GET.get('vehicle_type', None)  # Default None
    before = request.GET.get('before', None)  # Default to page 1
    sort = request.GET.get('sort', 'name')  # Default sort by name
    pass

def manual_entry(request):
    pass

def auto_detect(request):
    pass
