import json

from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from oauth2_provider.models import AccessToken

from yumfoodapp.models import Restaurant, Meal, Order, OrderDetails, Driver
from yumfoodapp.serializers import RestaurantSerializer, \
    MealSerializer, \
    OrderSerializer

import stripe
from yumfood.settings import STRIPE_API_KEY

stripe.api_key = STRIPE_API_KEY
####################
# CUSTOMERS
####################

def customer_get_restaurants(request):
    restaurants = RestaurantSerializer(
        Restaurant.objects.all().order_by("-id"),
        many = True,
        context = {"request":request}
    ).data

    return JsonResponse({"restaurants": restaurants})

def customer_get_meals(request, restaurant_id):
    meals = MealSerializer(
        Meal.objects.filter(restaurant_id = restaurant_id).order_by("-id"),
        many = True,
        context = {"request":request}
    ).data

    return JsonResponse({"meals": meals})

@csrf_exempt
def customer_add_order(request):
    """
        params:
            access_token
            restaurant_id
            address
            order_details (json format), example:
                [{"meal_id": 1, "quantity": 2},{"meal_id": 2, "quantity": 3}]
            stripe_token

        return:
            {"status": "success"}
    """
    if request.method == "POST":
        #Get(Obtener) Token
        access_token = AccessToken.objects.get(token = request.POST.get("access_token"),
            expires__gt = timezone.now())

        #Get(Obtener) profile
        customer = access_token.user.customer

        #Get stripe TOKEN
        stripe_token = request.POST["stripe_token"]


        #Compruebe si el cliente tiene algún pedido que no sea entregado
        if Order.objects.filter(customer = customer).exclude(status = Order.DELIVERED):
            return JsonResponse({"status":"failed","error": "Su ultimo pedido debe ser completado."})

        #verifique la dirección
        if not request.POST["address"]:
            return JsonResponse({"status":"failed","error": "La dirección es necesaria."})

        #Get(Obtener) Order Details
        order_details = json.loads(request.POST["order_details"])

        order_total = 0
        for meal in order_details:
            order_total += Meal.objects.get(id = meal["meal_id"]).price * meal["quantity"]
        if len(order_details) > 0:

            # Paso 1: Crear un cargo: esto cargará la tarjeta del cliente
            charge = stripe.Charge.create(
                amount = order_total * 100, #Amount in cents
                currency = "PEN",
                source = stripe_token,
                description = "YumFood Orden"
            )

            if charge.status != "failed":
                #Step 2 - Crear una orden
                order = Order.objects.create(
                    customer = customer,
                    restaurant_id = request.POST["restaurant_id"],
                    total = order_total,
                    status = Order.COOKING,
                    address = request.POST["address"]
                )
                #Step 3 - Crear orden detallada
                for meal in order_details:
                    OrderDetails.objects.create(
                        order = order,
                        meal_id = meal["meal_id"],
                        quantity = meal["quantity"],
                        sub_total = Meal.objects.get(id = meal["meal_id"]).price * meal["quantity"]
                    )

                return JsonResponse({"status": "success"})
            else:
                return JsonResponse({"status": "failed","error":"Fallo de conexión,"})



def customer_get_latest_order(request):
    access_token = AccessToken.objects.get(token = request.GET.get("access_token"),expires__gt = timezone.now())


    customer = access_token.user.customer
    order = OrderSerializer(Order.objects.filter(customer = customer).last()).data

    return JsonResponse({"order": order})

def customer_driver_location(request):
    access_token = AccessToken.objects.get(token = request.GET.get("access_token"),expires__gt = timezone.now())
    customer = access_token.user.customer

    #obtener la ubicación del conductor relacionada con el pedido actual de este cliente
    current_order = Order.objects.filter(customer = customer, status = Order.ONTHEWAY).last()
    location = current_order.driver.location

    return JsonResponse({"location": location})

####################
# RESTAURANT
####################

def restaurant_order_notification(request, last_request_time):
    notification = Order.objects.filter(restaurant = request.user.restaurant,
    create_at__gt = last_request_time).count()

    return JsonResponse({"notification": notification})


####################
# DRIVERS
####################

def driver_get_ready_orders(request):
    orders = OrderSerializer(
        Order.objects.filter(status = Order.READY, driver = None).order_by("-id"),
        many = True
    ).data
    return JsonResponse({"orders": orders})

@csrf_exempt
#POST params access_token, order_id
def driver_pick_order(request):
    if request.method == "POST":
        #GET TOKEN
        access_token = AccessToken.objects.get(token = request.POST.get("access_token"),
            expires__gt = timezone.now())

        #GET DRIVER
        driver = access_token.user.driver

        #verifica si el conductor solo puede recoger un pedido al mismo tiempo
        if Order.objects.filter(driver = driver).exclude(status = Order.ONTHEWAY):
            return JsonResponse({"status": "failed", "error": "Solo puedes elegir una orden al mismo tiempo."})

        try:
            order = Order.objects.get(
            id = request.POST["order_id"],
            driver = None,
            status = Order.READY
            )
            order.driver = driver
            order.status = Order.ONTHEWAY
            order.picked_at = timezone.now()
            order.save()

            return JsonResponse({"status":"success"})

        except Order.DoesNotExist:
            return JsonResponse({"status":"failed","error":"Este pedido ha sido recogido por otro"})

    return JsonResponse({})

#GET params access_token,
def driver_get_latest_order(request):
    #GET TOKEN
    access_token = AccessToken.objects.get(token = request.GET.get("access_token"),
        expires__gt = timezone.now())

    driver = access_token.user.driver
    order = OrderSerializer(
        Order.objects.filter(driver = driver).order_by("picked_at").last()
    ).data
    return JsonResponse({"order": order })

#POST params: access_token, order_id
@csrf_exempt
def driver_complete_order(request):
    access_token = AccessToken.objects.get(token = request.POST.get("access_token"),
        expires__gt = timezone.now())

    driver = access_token.user.driver

    order = Order.objects.get(id = request.POST["order_id"], driver = driver)
    order.status = Order.DELIVERED
    order.save()

    return JsonResponse({"status":"success"})

#GET params: access_token
def driver_get_revenue(request):
    access_token = AccessToken.objects.get(token = request.GET.get("access_token"),
        expires__gt = timezone.now())

    driver = access_token.user.driver

    from datetime import timedelta

    revenue = {}
    today = timezone.now()
    current_weekdays = [today + timedelta(days = i) for i in range(0 - today.weekday(), 7 - today.weekday())]

    for day in current_weekdays:
        orders = Order.objects.filter(
            driver = driver,
            status = Order.DELIVERED,
            create_at__year = day.year,
            create_at__month = day.month,
            create_at__day = day.day
        )

        revenue[day.strftime("%a")] = sum(order.total for order in orders)

    return JsonResponse({"revenue": revenue})

#POST - params: access_token, "Lat,Lng"
@csrf_exempt
def driver_update_location(request):
    if request.method == "POST":
        access_token = AccessToken.objects.get(token = request.POST.get("access_token"),
            expires__gt = timezone.now())

        driver = access_token.user.driver

        #AJUSTAR LA CADENA => DATABASE
        driver.location = request.POST["location"]
        driver.save()

        return JsonResponse({"status":"success"})
