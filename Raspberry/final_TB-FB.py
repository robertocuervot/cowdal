import os
import glob
import time
import RPi.GPIO as GPIO
import serial
import struct
import hashlib
import threading
import json
import csv
from mfrc522 import SimpleMFRC522
import Adafruit_ADS1x15
import paho.mqtt.client as mqtt
import pyrebase

GPIO.setwarnings(False)
# Configuración de pines
FLOW_SENSOR_PIN = 17  # Cambia este valor al pin GPIO que estés utilizando
VALVULA_PIN = 16
LED_AMARILLO = 21
LED_VERDE = 20
GPIO.setmode(GPIO.BCM)
GPIO.setup(FLOW_SENSOR_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(VALVULA_PIN, GPIO.OUT)
GPIO.setup(LED_AMARILLO, GPIO.OUT)
GPIO.setup(LED_VERDE, GPIO.OUT)

# Variables para cálculos de flujo
flow_rate = 0.0
total_liters = 0.0
last_tick = time.time()
ML_PER_LITER = 1000  # Pulsos por litro del sensor

#Sensor ph
adc_ph = Adafruit_ADS1x15.ADS1115()
channel_ph = 0
value_ph = 0
value_ph_valve = 0

#Sensor nfc
nfc = SimpleMFRC522()
codigo=""

#Temperatura
c_valve=0

#Bandera para finalizar la lectura
finalizar=False

# Configuracion Firebase
config = {
    "apiKey": "AIzaSyCa5cUxigr4rnuI2ioLT-JM8XJfGgMXi4E",
    "authDomain": "cow-dal.firebaseapp.com",
    "databaseURL": "https://cow-dal-default-rtdb.firebaseio.com",
    "storageBucket": "cow-dal.appspot.com"
}

firebase = pyrebase.initialize_app(config)
# Autentica tu aplicación con un usuario de Firebase
email = "p@p.com"
password = "123456789aA$"
auth = firebase.auth()
user = auth.sign_in_with_email_and_password(email, password)

db = firebase.database()

#Declaracion para comunicación con ThingsBoard
THINGSBOARD_HOST = 'demo.thingsboard.io'
ACCESS_TOKEN = ['Q5TR7p7viQXXKb4MeIMk','EAS27cstjbo6GSpXq4oo']

# Topico para enviar datos a telemtria
topic = 'v1/devices/me/telemetry'

# Crear cliente MQTT para cada hilo
temp_client = mqtt.Client()
flow_client = mqtt.Client()
ph_client = mqtt.Client()
control_client = mqtt.Client()

# Configuración para ver estado de pines de la Raspberry
gpio_state = {7: False, 11: False, 12: False, 13: False, 15: False, 16: False, 18: False, 22: False, 29: False,
              31: False, 32: False, 33: False, 35: False, 36: False, 37: False, 38: False, 40: False}

# Función para verificar la conexión con widget de Raspberry
def on_connect(client, userdata, rc, *extra_params):
    print('Connected with result code ' + str(rc))
    # Subscribing to receive RPC requests
    client.subscribe('v1/devices/me/rpc/request/+')
    # Sending current GPIO status
    client.publish('v1/devices/me/attributes', get_gpio_status(), 1)

# Función para manejar el mensaje recibido desde el servidor
def on_message(client, userdata, msg):
    print ('Topic: ' + msg.topic + '\nMessage: ' + str(msg.payload))
    # Decode JSON request
    data = json.loads(msg.payload)
    # Check request method
    if data['method'] == 'getGpioStatus':
        # Reply with GPIO status
        client.publish(msg.topic.replace('request', 'response'), get_gpio_status(), 1)
    elif data['method'] == 'setGpioStatus':
        # Update GPIO status and reply
        set_gpio_status(data['params']['pin'], data['params']['enabled'])
        client.publish(msg.topic.replace('request', 'response'), get_gpio_status(), 1)
        client.publish('v1/devices/me/attributes', get_gpio_status(), 1)

def get_gpio_status():
    # Encode GPIOs state to json
    return json.dumps(gpio_state)

def set_gpio_status(pin, status):
    # Output GPIOs state
    GPIO.output(pin, GPIO.HIGH if status else GPIO.LOW)
    # Update GPIOs state
    gpio_state[pin] = status
    
# Función que permite el control desde ThingsBoard
def main_control():
    try:
        control_client.loop_forever()
    except KeyboardInterrupt:
        print("Control finalizado por el usuario")

#Función para la lectura de ph
def main_ph():
    try:
        ph_client.loop_start()
        # Obtén la colección
        uid = user['localId']
        while True:
            global value_ph_valve
            value_ph = adc_ph.read_adc(channel_ph)
            value_ph = (value_ph*14)/65536
            value_ph_valve = value_ph
            print("Valor ph: ", value_ph)
            current_time_ph = time.strftime('%Y-%m-%d %H:%M:%S')
            # Aqui empieza el envio de datos a ThingsBoard
            sensor_data = {'ph': 0}
            ph_mqtt = str(value_ph)
            sensor_type = "1"
            units = "ph"
            sensor_data['ph'] = ph_mqtt
            ph_client.publish(topic, json.dumps(sensor_data), 1)
            # Comunicación Firebase
            sensor_types = 1
            data = {
            "id": codigo,
            "measure": value_ph,
            "timesatam": current_time_ph,
            "type": sensor_types,
            "unit": units
            }
            # Añade los datos a la colección
            collection = db.child("granja").child(uid).child("data")
            collection.push(data)
            
            time.sleep(1)
    except KeyboardInterrupt:
        print("Lectura de pH finalizada por el usuario")


def read_temp_raw():
    with open(device_path + '/w1_slave', 'r') as f:
        valid, temp = f.readlines()
    return valid, temp

def read_temp():
    valid, temp = read_temp_raw()

    while 'YES' not in valid:
        time.sleep(0.2)
        valid, temp = read_temp_raw()

    pos = temp.index('t=')
    if pos != -1:
        temp_string = temp[pos+2:]
        temp_c = float(temp_string) / 1000.0 
        temp_f = temp_c * (9.0 / 5.0) + 32.0
        return temp_c, temp_f

def pulse_callback(channel):
    global last_tick, flow_rate, total_liters
    tick = time.time()
    elapsed = tick - last_tick
    last_tick = tick
    flow_rate = (1.0 / elapsed)
    total_liters += 1.0/480.0

def main_temp():
    try:
        temp_client.loop_start()
        # Obtén la colección
        uid = user['localId']
        while True:
            global c_valve
            c, f = read_temp()
            timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
            c_valve = c
            # Imprime y guarda la temperatura en el archivo CSV
            print('C={:,.3f}'.format(c))
            # Aqui empieza el envio de datos a ThingsBoard
            sensor_data = {'temperatura': 0}
            c_mqtt = str(c)
            sensor_type = "0"
            units = "°C"
            sensor_data['temperatura'] = c_mqtt
            temp_client.publish(topic, json.dumps(sensor_data), 1)
            # Aqui empieza el envio de datos a Firebase
            sensor_types = 0
            data = {
            "id": codigo,
            "measure": c,
            "timesatam": timestamp,
            "type": sensor_types,
            "unit": units
            }

            # Añade los datos a la colección
            collection = db.child("granja").child(uid).child("data")
            collection.push(data)
            
            time.sleep(1)
    except KeyboardInterrupt:
        print("Lectura de temperatura finalizada por el usuario")
        
def main_valve():

    try:
        while True:
            global value_ph_valve
            global c_valve
            if c_valve >=35.0:
                GPIO.output(VALVULA_PIN,False)
                print('Valvula Cerrada')
                print(format(c_valve))
            elif c_valve < 35.0:
                GPIO.output(VALVULA_PIN,True)
                print('Valvula Abierta')
                print(format(c_valve))
            
            time.sleep(1)
    except KeyboardInterrupt:
        print("Lectura de temperatura finalizada por el usuario")
        
#Main para la lectura de flujo
def main_flow():
    global last_tick, flow_rate, total_liters
    try:
        flow_client.loop_start()
        # Obtén la colección
        uid = user['localId']
        GPIO.add_event_detect(FLOW_SENSOR_PIN, GPIO.RISING, callback=pulse_callback, bouncetime=20)
        while True:
            start_time = time.time()
            print(f"Flujo: {flow_rate:.2f} mL/s - Total acumulado: {total_liters:.2f} litros")
            current_time_flow = time.strftime('%Y-%m-%d %H:%M:%S')
            # Aqui empieza el envio de datos a ThingsBoard
            sensor_data = {'litros': 0}
            liters_mqtt = str(total_liters)
            sensor_type = "2"
            units = "L"
            sensor_data['litros'] = liters_mqtt
            flow_client.publish(topic, json.dumps(sensor_data), 1)
            # Aqui empieza el envio de datos a Firebase
            sensor_types = 2
            data = {
            "id": codigo,
            "measure": flow_rate,
            "timesatam": current_time_flow,
            "type": sensor_types,
            "unit": units
            }

            # Añade los datos a la colección
            collection = db.child("granja").child(uid).child("data")
            collection.push(data)
            print("ID: ", codigo)
            
            time.sleep(0.2)
    except KeyboardInterrupt:
        print("Lectura de flujo finalizada por el usuario")
        GPIO.cleanup()
#Main NFC        
def main_nfc():
    GPIO.output(LED_AMARILLO,True)
    GPIO.output(LED_VERDE,False)
    id, text = nfc.read() #Lectura del id del tag y mensaje que contiene
    print(id)
    print(text)
    return text

#Funcion para parar la lectura de datos
def stop_program():
    try:
        
        while True:
            print("Esperando lectura NFC para detener el programa...")
            id_stop, text_stop = nfc.read()
            if text_stop:
                print("Deteniendo el programa...")
                GPIO.cleanup()
                finalizar=True
                os._exit(0)
            time.sleep(2)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    #global codigo
    os.system('modprobe w1-gpio')
    os.system('modprobe w1-therm')
    base_dir = '/sys/bus/w1/devices/'
    device_path = glob.glob(base_dir + '28*')[0]
    rom = device_path.split('/')[-1]

    print('ROM: ' + rom)
    codigo1=main_nfc()# Bandera de inicio de los hilos, es decir, recopilación de datos con sensores
    codigo=codigo1.strip()# Codigo es el id de las vacas
    no_vaca = int(codigo) - 1
    
    # Register connect callback
    control_client.on_connect = on_connect
    # Registed publish message callback
    control_client.on_message = on_message
    
    # Configuracion del username (en el caso de TB es el ACCESS TOKEN)
    temp_client.username_pw_set(ACCESS_TOKEN[no_vaca])
    flow_client.username_pw_set(ACCESS_TOKEN[no_vaca])
    ph_client.username_pw_set(ACCESS_TOKEN[no_vaca])
    control_client.username_pw_set(ACCESS_TOKEN[no_vaca])

    # Conexion a ThingsBoard usando MQTT con 60 segundos de duracion de la sesion (keepalive interval)
    temp_client.connect(THINGSBOARD_HOST, 1883, 60)
    flow_client.connect(THINGSBOARD_HOST, 1883, 60)
    ph_client.connect(THINGSBOARD_HOST, 1883, 60)
    control_client.connect(THINGSBOARD_HOST, 1883, 60)
    
    #Inicializacion de hilos con los distintos programas princilaes de los sensores
    temperature_thread = threading.Thread(target=main_temp)#Inicio hilo temperatura
    flow_thread = threading.Thread(target=main_flow)#Inicio hilo temperatura
    ph_thread = threading.Thread(target=main_ph)#Inicio hilo temperatura
    valve_thread = threading.Thread(target=main_valve)
    control_thread = threading.Thread(target=main_control)
    stop_thread = threading.Thread(target=stop_program)
    print('Hago Threads')
    GPIO.output(LED_AMARILLO,False)
    GPIO.output(LED_VERDE,True)
    
    #Inicio de los hilos
    temperature_thread.start()
    flow_thread.start()
    ph_thread.start()
    valve_thread.start()
    control_thread.start()
    time.sleep(2)
    stop_thread.start()

    try:
        temperature_thread.join()
        flow_thread.join()
        ph_thread.join()
        valve_thread.join()
        control_thread.join()
        stop_thread.join()
        GPIO.cleanup()
        if(finalizar):
            temp_client.loop_stop()
            temp_client.disconnect()
            flow_client.loop_stop()
            flow_client.disconnect()
            ph_client.loop_stop()
            ph_client.disconnect()
            os._exit(0)
            
    except KeyboardInterrupt:
        print("Deteniendo la lectura de sensores.")
        GPIO.cleanup()

