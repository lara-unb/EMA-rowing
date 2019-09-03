"""
This scripts open socket connections to receive data from other programs and save them with a unified timestamp.
It is useful for syncing data from different sources.
It has a real time plot if desired that must be customized if used.
Right now it is set to open:
- python processing socket connection to receive data from other python scripts, particularly IMU data
- 2 regular TCPIP socket connections to receive data from non python programs, particularly EMG data from MATLAB.
Author: Lucas Fonseca
Contact: lucasafonseca@lara.unb.br
Date: Feb 25th 2019
Last update: April 12th 2019
"""

# this is the server
import time
from multiprocessing.connection import Listener
import socket
import multiprocessing
import sys
import datetime
import struct
import math
import pyqtgraph as pg
from pyqtgraph.Qt import QtGui, QtCore
from pyquaternion import Quaternion
import json
import numpy as np

#exclude
from pypreprocessor import pypreprocessor
# run the lowpass filter in angle signal for velocity calculation
#pypreprocessor.defines.append('lowpass')

# calculate velocity with min and max values
#pypreprocessor.defines.append('minmax')

# calculate velocity with crossing mean values
#pypreprocessor.defines.append('cross_mean')

# calculate velocity with amplitude or derivative, or only with period
#pypreprocessor.defines.append('period_only')

#calculate velocity with predominant frequency of Fourier transform of the signal
pypreprocessor.defines.append('fourier')

# calculate velocity with delay
#pypreprocessor.defines.append('delay')

# print velocity calculation data
pypreprocessor.defines.append('velocity_print')

pypreprocessor.output = 'main_data_out.py'
pypreprocessor.removeMeta = True
pypreprocessor.run = False
pypreprocessor.parse()
#endexclude

real_time_plot = False

# x and y are used to graph results in real time
size_of_graph = 10000
t = multiprocessing.Array('d', size_of_graph)
ang = multiprocessing.Array('d', size_of_graph)
fes = multiprocessing.Array('d', size_of_graph)
running = multiprocessing.Value('b')
start_time = time.time()
startup_velocity = False
velocity_queue = multiprocessing.Queue()
if real_time_plot:

    imu1_id = 8
    imu2_id = 3
    for i in range(size_of_graph):
        t[i] = 0
        ang[i] = 0

    # global curve_x, t, curve_y, ang
    app = QtGui.QApplication([])
    win = pg.GraphicsWindow(title="Basic plotting examples")
    win.resize(1000, 600)
    win.setWindowTitle('pyqtgraph example: Plotting')
    pg.setConfigOptions(antialias=True)
    my_plot = win.addPlot(title="Updating plot")

    # my_plot.setRange(xRange=(0, size_of_graph/10), yRange=(-20, 400))
    # my_plot.enableAutoRange('xy', False)


    curve_x = my_plot.plot(x = t, pen='b')
    curve_y = my_plot.plot(x = t, pen='r')


    # x = [0] * 1000
    # ptr = 0

    def update():
        global curve_x, t, curve_y, ang
        # print('New data: ', x[-1])
        # print('New data: ', ang[-1])

        curve_x.setData(t[-size_of_graph:], ang[-size_of_graph:])
        #curve_y.setData(t[-size_of_graph], fes[-size_of_graph:])
        calculate_fourier = True
        if calculate_fourier:
            freq_sample_size = 100
            sp = np.fft.fft(ang[-freq_sample_size:])
            freq = np.fft.fftfreq(freq_sample_size, (t[-1]-t[-freq_sample_size])/(freq_sample_size-1))
            curve_y.setData(freq, sp.imag*max(np.abs(ang[-size_of_graph:]))/max(np.abs(sp.imag)))
            print('Main freq -', freq[np.where(sp.imag == np.amax(sp.imag))[0]])
        # ptr = 0
        # if ptr == 0:
        #     my_plot.enableAutoRange('xy', False)  ## stop auto-scaling after the first data set is plotted
        # ptr += 1


    timer = QtCore.QTimer()
    timer.timeout.connect(update)
    timer.start(15)


def on_exit(sig, frame):
    # global imu_data
    # print(imu_data)
    # now = datetime.datetime.now()
    # filename = now.strftime('%Y%m%d%H%M') + '_IMU_data.txt'
    # f = open(filename, 'w+')
    # [f.write(i) for i in imu_data]
    # f.close()
    print('Good bye')
    sys.exit(0)


def calculate_distance(q0, q1):

    # I think this one works
    # new_angle = 2 * Quaternion.distance(q0, q1) * 180 / math.pi
    #
    # if q0.elements[2] >= q1.elements[2]:
    #     signal = 1
    # else:
    #     signal = -1
    #
    # if new_angle > 180:
    #     new_angle = 360 - new_angle
    # new_angle = new_angle * signal

    # This one works!
    # new_angle = q0.conjugate * q1
    # new_angle = 2 * math.atan2(math.sqrt(math.pow(new_angle.vector[0], 2) +
    #                                      math.pow(new_angle.vector[1], 2) +
    #                                      math.pow(new_angle.vector[2], 2)),
    #                            new_angle.real)
    #
    # new_angle = new_angle * 180 / math.pi
    # if new_angle > 180:
    #     new_angle = 360 - new_angle

    # The best!!!
    try:
        new_quat = q0 * q1.conjugate
        qr = new_quat.elements[0]
        if qr > 1:
            qr = 1
        elif qr < -1:
            qr = -1
        new_angle = 2 * math.acos(qr)
        new_angle = new_angle * 180 / math.pi
        if new_angle > 180:
            new_angle = 360 - new_angle

    except Exception as e:
        print('Error calculation angle: ' + str(e) + 'on line ' + str(sys.exc_info()[2].tb_lineno))
        print('qr = {}'.format(new_quat.elements[0]))

    return new_angle


def do_stuff(client, source, t, ang, fes, start_time, running, imu_data):
    def save_data():
        now = datetime.datetime.now()
        filename = now.strftime('%Y%m%d%H%M%S') + '_' + source + '_data.txt'
        f = open(filename, 'w+')
        # server_timestamp, client_timestamp, msg
        # if IMU, msg = id, quaternions
        # if buttons, msg = state, current
        [f.write(str(i)[1:-1].replace('[', '').replace(']', '') + '\r\n') for i in server_data]
        f.close()

    imu1 = [Quaternion(1, 0, 0, 0)]
    imu2 = [Quaternion(1, 0, 0, 0)]
    def update_plot():
        global t, ang, fes, start_time, startup_velocity, velocity_queue

        t[0:-1] = t[1:]
        t[-1] = time.time() - start_time

        # print(source)
        if source == 'imus':
            new_quat = Quaternion(data[2], data[3], data[4], data[5])
            id = data[1]

            if id == imu1_id:
                imu1.append(new_quat)
            elif id == imu2_id:
                imu2.append(new_quat)
            else:
                # print('ID not known')
                return

            #new_angle = calculate_distance(imu1[-1], imu2[-1])
            new_angle = quat2euler(data[2:6])
            
            ang[0:-1] = ang[1:]
            #ang[-1] = new_angle
            ang[-1] = new_angle[1]

            fes[0:-1] = fes[1:]
            fes[-1] = fes[-2]


        elif source == 'stim':
            # print('update stim')
            stim_state = data[1]
            state = 0
            if stim_state == 'stop':
                state = 0
            elif stim_state == 'extension':
                state = 1
            elif stim_state == 'flexion':
                state = -1
            fes[0:-1] = fes[1:]
            fes[-1] = state * 45 + 45

            ang[0:-1] = ang[1:]
            ang[-1] = ang[-2]

    server_data = []

    try:
        while running.value:
            data = client.recv()
            if not data == '':
                server_data.append([time.time(), data])
                imu_data[data[1]] = data[:]+['|']
                if data[1] == 8:
                    startup_velocity = True
                    velocity_queue.put(data)
                    #print('{}'.format(source), ' - ', data[1], ' ', time.time() - start_time)
                # print('received stim data')
                if real_time_plot:
                    update_plot()

        save_data()

    except Exception as e:
        print('Exception raised: ', str(e), ', on line ', str(sys.exc_info()[2].tb_lineno))
        print('Connection  to {} closed'.format(source))
        save_data()


def do_stuff_socket(client, source, x, channel):
    # global x
    server_data = []
    # signal.signal(signal.SIGINT, on_exit)
    # now = time.time()

    try:
        while True:
            # print(address)
            # time.sleep(1)
            data = client.recv(4096)
            if len(data) > 2:
                # print('Data: ', data)
                # print('Data length: ', len(data))
                number_of_packets = math.floor(len(data) / 8)
                # print(number_of_packets)
                packets = []
                for i in range(number_of_packets):
                    this_packet = float(struct.unpack('!d', data[i * 8:i * 8 + 8])[0])
                    packets.append(this_packet)
                    # print('Double: ', this_packet)
                # for i in range(len(data)-3):
                #     print('Float from byte ', i, ': ', struct.unpack('!f', data[i:i+4]))
                # print('First 4 bytes unpacked: ',struct.unpack('!f', data[0:4]))
                # print('Last 4 bytes unpacked: ', struct.unpack('!f', data[-4:]))
                # print('')
                # x.append(packets)
                if channel == 1:
                    x[0:-number_of_packets] = x[number_of_packets:]
                    x[-number_of_packets:] = packets
                elif channel == 2:
                    y[0:-number_of_packets] = y[number_of_packets:]
                    y[-number_of_packets:] = packets
                server_data.append([time.time(), packets])
                # print(packets[0])
                # print(imu_data)
                # print(source, data)
                # time.sleep(1)
            else:
                raise ValueError('Connection closed')
            # print(1/(time.time()-now))
            # now = time.time()
    except Exception as e:
        print('Exception raised: ', str(e), ', on line ', str(sys.exc_info()[2].tb_lineno))
        print('Connection  to {} closed'.format(source))
        now = datetime.datetime.now()
        filename = now.strftime('%Y%m%d%H%M') + '_' + source + '_ch' + str(channel) + '_data.txt'
        f = open(filename, 'w+')
        # server_timestamp, client_timestamp, msg
        # if IMU, msg = id, quaternions
        # if buttons, msg = state, current
        [f.write(str(i)[1:-1].replace('[', '').replace(']', '') + '\r\n') for i in server_data]
        f.close()


def server(address, port, t, ang, fes, start_time, running, imu_data):
    serv = Listener((address, port))
    # s = socket.socket()
    # s.bind(address)
    # s.listen()
    while running.value:
        # print(running.value)
        # client, addr = s.accept()
        client = serv.accept()
        print('Connected to {}'.format(serv.last_accepted))
        source = client.recv()
        print('Source: {}'.format(source))
        p = multiprocessing.Process(target=do_stuff, args=(client, source, t, ang, fes, start_time, running, imu_data))
        # do_stuff(client, addr)
        p.start()

        # signal.pause()
    print('End of process server')


def socket_server(address, port, x, channel):
    s = socket.socket()
    s.bind((address, port))
    s.listen()
    while True:
        conn, addr = s.accept()
        print('Connected to {}'.format(addr))
        time.sleep(1)
        if s:
            source = str(conn.recv(4096))[2:-1]
            if len(source) > 20:
                source = 'EMG'
        else:
            print('Disconnected from {}'.format(addr))
            break
        print('Source: {}'.format(source))
        p = multiprocessing.Process(target=do_stuff_socket, args=(conn, source, x, channel))
        # do_stuff(client, addr)
        p.start()

def vr_server(address, port, imu_data):
    # global imu_data
    while True:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((address, port))
            s.listen()
            conn, addr = s.accept()
            if s:
                print('Connected to {}'.format(addr))
                source = str(conn.recv(4096))[2:-1]
                if source != 'VR':
                    continue
                print('Source: {}'.format(source))
            while True:
                # print('Connection attempt')
                receiveTime = str(conn.recv(4096))[2:-1]
                # print('Connection attempt 1')
                # time.sleep(1/720)
                # print('Connection attempt 2')
                if s:
                    # imu_data.append([time.time(), imu_data])
                    # print('Sent message: {}'.format(list(imu_data)))
                    # imu_data[:] = [float(receiveTime), imu_data[:]]
                    out_data = json.dumps(receiveTime + '|') + json.dumps(dict(imu_data))
                    conn.send(out_data.encode())
                    # del imu_data[:]
                    # print(out_data)
                else:
                    print('Disconnected from {}'.format(addr))
                    break

        except Exception as e:
            print('VR - Exception raised: ', str(e), ', on line ', str(sys.exc_info()[2].tb_lineno))
            print('Connection  to {} closed'.format(source))

def quat2euler(input_quat):
    if isinstance(input_quat, Quaternion):
        q = input_quat.elements
    elif len(input_quat) == 4:
        q = input_quat
    else:
        q = [1, 0, 0, 0]
        print('Invalid quaternion!')
    
    (x, y, z, w) = (q[0], q[1], q[2], q[3])
    t0 = +2.0 * (w * x + y * z)
    t1 = +1.0 - 2.0 * (x * x + y * y)
    roll = math.atan2(t0, t1) * 180/math.pi
    t2 = +2.0 * (w * y - z * x)
    t2 = +1.0 if t2 > +1.0 else t2
    t2 = -1.0 if t2 < -1.0 else t2
    pitch = math.asin(t2) * 180/math.pi
    t3 = +2.0 * (w * z + x * y)
    t4 = +1.0 - 2.0 * (y * y + z * z)
    yaw = math.atan2(t3, t4) * 180/math.pi
    
    return [roll, pitch, yaw]

def velocity_calculation(address, imu_data, stim_leg):
    import numpy as np
    from scipy.signal import filtfilt, butter
    
    signal_change = [] # Store time and value of signal when sign of derivative changes
    mean_crossing_samples = [] # Samples of the signal that cross the mean value, including time, value, period and derivative
    orientation_signal = [] # Store the orientation signal of IMU
    last_positive_concavity = -1 # Store the position of last point in signal_change with positive concavity
    last_positive_concavity_applied = -1 # Store the position of last sample in signal_change with positive concavity used to calculate velocity
    last_negative_concavity = -1 # Store the position of last point in signal_change with negative concavity
    last_negative_concavity_applied = -1  # Store the position of last point in signal_change with negative concavity used to calculate velocity
    minimum_period = 0.33 # Minimum time allowed between samples in signal_change to calculated velocity
    calculated_velocity = 0
    initial_time = 0
    sample_rate = 100
    min_vel_delay = 0.25
    fourier_counter = 0
    
    while True:
        try:
            thread_start_time = time.time()
            queue_data = velocity_queue.get()
            # Wait and execute when there is new IMU sample
            if queue_data != None:
                queue_data.extend(quat2euler(queue_data[2:6])) # Append Euler angles data
                orientation_signal.append({'time':queue_data[0], 'value':queue_data[-2]})
#ifdef velocity_print
                print('Velocity Calculation - ', str(queue_data[1]), ' ', str(queue_data[-2]))
#endif
                if len(orientation_signal) > 1:
                    # Resample time with constant sample rate
                    orientation_signal[-1]['resampled_time'] = round((orientation_signal[-1]['time'] - initial_time)*sample_rate)/sample_rate
                    
                    # Remove sample with repeated resampled_time
                    # if orientation_signal[-1]['resampled_time'] = orientation_signal[-2]['resampled_time']
                        # del orientation_signal[-2]
                        # if last_positive_concavity >= 0:
                            # last_positive_concavity = last_positive_concavity - 1
                        
                        # if last_positive_concavity_applied >= 0:
                            # last_positive_concavity_applied = last_positive_concavity_applied - 1
                        
                        # if last_negative_concavity >= 0:
                            # last_negative_concavity = last_negative_concavity - 1
                        
                        # if last_negative_concavity_applied >= 0:
                            # last_negative_concavity_applied = last_negative_concavity_applied - 1

                        # continue
                    
                    # Calculate discrete derivative of the orientation signal
                    orientation_signal[-1]['derivative'] = (orientation_signal[-1]['value']-orientation_signal[-2]['value']) / (orientation_signal[-1]['time']-orientation_signal[-2]['time'])
                    
                elif len(orientation_signal) == 1:
                    # Resampled time is the same as the true time in the first sample
                    initial_time = orientation_signal[-1]['time']
                    orientation_signal[-1]['resampled_time'] = initial_time
                
#ifdef lowpass
                if (len(orientation_signal) > 0) and ((len(orientation_signal) % sample_rate) == 0):
                    #Apply Butterworth lowpass filter in the last sample_rate samples
                    x = []
                    for i in range(-sample_rate, 0):
                        x.append(orientation_signal[i]['value'])
                            
                    nyquist = sample_rate/2
                    order = 25
                    cutoff = 12.5
                    [b, a] = butter(order, cutoff / nyquist)
                    if np.all(np.abs(np.roots(a)) < 1):
                        filtered = filtfilt(b, a, x, method='pad')
                        for i in range(-sample_rate, 0):
                            orientation_signal[i]['filtered_value'] = filtered[i]
                            
                            if (i != -sample_rate) or (len(orientation_signal) > sample_rate):
                                orientation_signal[i]['derivative'] = (orientation_signal[i]['filtered_value']-orientation_signal[i-1]['filtered_value']) / (orientation_signal[i]['resampled_time']-orientation_signal[i-1]['resampled_time'] if orientation_signal[i]['resampled_time']-orientation_signal[i-1]['resampled_time'] > 0.5/sample_rate else 1/sample_rate)


                    for i in range(-(sample_rate - 1) if len(orientation_signal) > sample_rate else -(sample_rate - 2), 0):
                        pass
#else
                if len(orientation_signal) > 2:
                    for i in range(-1,0):
                        pass
#endif
                        # Find the points in orientation signal when sign of derivative changes (-/+) and store in signal_change
                        if (orientation_signal[i-1]['derivative'] <= 0 and orientation_signal[i]['derivative'] > 0) or (orientation_signal[i-1]['derivative'] < 0 and orientation_signal[i]['derivative'] >= 0):
                            signal_change.append({'time' : orientation_signal[i]['time'], 'concavity' : 1, 'value' : orientation_signal[i]['value']})
#ifdef minmax
                            # Apply the period as the difference between current and last_positive_concavity(_applied) time samples
                            if last_positive_concavity >= 0 and signal_change[-1]['time'] - signal_change[last_negative_concavity]['time'] > minimum_period and (last_negative_concavity == 0 or signal_change[-1]['time'] - signal_change[last_negative_concavity]['time'] > minimum_period/3):
                                signal_change[-1]['period'] = signal_change[-1]['time'] - signal_change[last_positive_concavity_applied if last_positive_concavity_applied >= 0 else last_positive_concavity]['time']

                                # Apply the amplitude as the difference between current and last_negative_concavity(_applied) value samples
                                if last_negative_concavity >= 0:
                                    signal_change[-1]['amplitude'] = abs(signal_change[-1]['value'] - signal_change[last_negative_concavity_applied if last_negative_concavity_applied >= 0 else last_negative_concavity]['value'])
                                    
                                # Apply the velocity as amplitude divided by period
                                if last_negative_concavity >= 0 and (last_positive_concavity_applied < 0 or signal_change[-1]['period'] > minimum_period):
#ifdef delay
                                    #When calculating, the last signal_change may not be the lowest or highest value, so it is used a delayed sample
                                    selected_signal_change = [dic for dic in signal_change if dic['concavity'] == 1 and 'amplitude' in dic]
                                    for delayed_sample in range(0,len(selected_signal_change) - 1):
                                        posterior_samples = [dic['value'] for dic in selected_signal_change][delayed_sample+1:len(selected_signal_change)]
                                        if selected_signal_change[delayed_sample]['concavity'] == 1 and selected_signal_change[-1]['time'] - selected_signal_change[delayed_sample]['time'] >= min_vel_delay and selected_signal_change[-1]['time'] - selected_signal_change[delayed_sample + 1]['time'] < min_vel_delay and (len(posterior_samples) == 0 or selected_signal_change[delayed_sample]['value'] < min(posterior_samples)):
#ifdef period_only
                                            calculated_velocity = 1/selected_signal_change[delayed_sample]['period']
#else
                                            calculated_velocity = selected_signal_change[delayed_sample]['amplitude']/selected_signal_change[delayed_sample]['period']
#endif
                                            stim_leg[0] = 1
                                            break
#else
#ifdef period_only
                                    calculated_velocity = 1/signal_change[-1]['period']
#else
                                    calculated_velocity = signal_change[-1]['amplitude']/signal_change[-1]['period']
#endif
                                    stim_leg[0] = 1
#endif
                                    
#ifdef velocity_print
#ifdef delay
                                    print('Calculated Velocity Positive -', selected_signal_change[delayed_sample]['amplitude'], selected_signal_change[delayed_sample]['period'])
#else
                                    print('Calculated Velocity Positive -', signal_change[-1]['amplitude'], signal_change[-1]['period'])
#endif
#endif
                                    imu_data['velocity'] = str(calculated_velocity) + '|'
                                    last_positive_concavity_applied =  len(signal_change) - 1
#endif
                                
                            last_positive_concavity = len(signal_change) - 1
                        
                        # Find the points in orientation signal when sign of derivative changes (+/-) and store in signal_change
                        elif (orientation_signal[i-1]['derivative'] >= 0 and orientation_signal[i]['derivative'] < 0) or (orientation_signal[i-1]['derivative'] > 0 and orientation_signal[i]['derivative'] <= 0):
                            signal_change.append({'time' : orientation_signal[i]['time'], 'concavity' : 0, 'value' : orientation_signal[i]['value']})
#ifdef minmax
                            # Apply the period as the difference between current and last_negative_concavity(_applied) time samples
                            if last_negative_concavity >= 0 and signal_change[-1]['time'] - signal_change[last_negative_concavity]['time'] > minimum_period and (last_positive_concavity == 0 or signal_change[-1]['time'] - signal_change[last_positive_concavity]['time'] > minimum_period/3):
                                signal_change[-1]['period'] = signal_change[-1]['time'] - signal_change[last_negative_concavity_applied if last_negative_concavity_applied >= 0 else last_negative_concavity]['time']
                                
                                # Apply the amplitude as the difference between current and last_positive_concavity(_applied) value samples
                                if last_positive_concavity >= 0:
                                    signal_change[-1]['amplitude'] = abs(signal_change[-1]['value'] - signal_change[last_positive_concavity_applied if last_positive_concavity_applied >= 0 else last_positive_concavity]['value'])
                                
                                # Apply the velocity as amplitude divided by period
                                if (last_negative_concavity_applied < 0 or signal_change[-1]['period'] > minimum_period) and last_positive_concavity >= 0:
#ifdef delay
                                    #When calculating, the last signal_change may not be the lowest or highest value, so it is used a delayed sample
                                    selected_signal_change = [dic for dic in signal_change if dic['concavity'] == 0 and 'amplitude' in dic]
                                    for delayed_sample in range(0,len(selected_signal_change) - 1):
                                        posterior_samples = [dic['value'] for dic in selected_signal_change][delayed_sample+1:len(selected_signal_change)]
                                        if selected_signal_change[delayed_sample]['concavity'] == 0 and selected_signal_change[-1]['time'] - selected_signal_change[delayed_sample]['time'] >= min_vel_delay and selected_signal_change[-1]['time'] - selected_signal_change[delayed_sample + 1]['time'] < min_vel_delay and (len(posterior_samples) == 0 or selected_signal_change[delayed_sample]['value'] > max(posterior_samples)):
#ifdef period_only
                                            calculated_velocity = 1/selected_signal_change[delayed_sample]['period']
#else
                                            calculated_velocity = selected_signal_change[delayed_sample]['amplitude']/selected_signal_change[delayed_sample]['period']
#endif
                                            stim_leg[0] = -1
                                            break
#else
#ifdef period_only
                                    calculated_velocity = 1/signal_change[-1]['period']
#else
                                    calculated_velocity = signal_change[-1]['amplitude']/signal_change[-1]['period']
#endif
                                    stim_leg[0] = -1
#endif

#ifdef velocity_print
#ifdef delay
                                    print('Calculated Velocity Negative -', selected_signal_change[delayed_sample]['amplitude'], selected_signal_change[delayed_sample]['period'])
#else
                                    print('Calculated Velocity Negative -', signal_change[-1]['amplitude'], signal_change[-1]['period'])
#endif
#endif
                                    imu_data['velocity'] = str(calculated_velocity) + '|'
                                    last_negative_concavity_applied = len(signal_change) - 1
#endif
                            
                            last_negative_concavity = len(signal_change) - 1
                    
                    maximum_list = [dic['value'] for dic in signal_change if dic['concavity'] == 0][-10 if len(signal_change) >= 10 else -len(signal_change) : -1]
                    mean_maximum = np.mean(maximum_list)
                    stdev_maximum = np.std(maximum_list)
                    mean_maximum = np.mean([dic['value'] for dic in signal_change if dic['concavity'] == 0 and mean_maximum - stdev_maximum < dic['value'] < mean_maximum + stdev_maximum][-10 if len(signal_change) >= 10 else -len(signal_change) : -1]) # Filter the values to +/-stdev around the mean and find a new mean
                    
                    minimum_list = [dic['value'] for dic in signal_change if dic['concavity'] == 1][-10 if len(signal_change) >= 10 else -len(signal_change) : -1]
                    mean_minimum = np.mean(minimum_list)
                    stdev_minimum = np.std(minimum_list)
                    mean_minimum = np.mean([dic['value'] for dic in signal_change if dic['concavity'] == 1 and mean_minimum - stdev_minimum < dic['value'] < mean_minimum + stdev_minimum][-10 if len(signal_change) >= 10 else -len(signal_change) : -1]) # Filter the values to +/-stdev around the mean and find a new mean
                    
                    mean_signal_value = (mean_maximum + mean_minimum)/2
                    # print('Signal change: ', signal_change[-3]['value'], ' ', signal_change[-2]['value'], ' ', signal_change[-1]['value'], ' ')
                    # print('Minimum list: ', minimum_list)
                    # print('Maximum list: ', maximum_list)
                    # print('Minimum mean and stdev: ', mean_minimum, ' ', stdev_minimum)
                    # print('Maximum mean and stdev: ', mean_maximum, ' ', stdev_maximum)
                    # print('Mean signal value - ', mean_signal_value)
#ifdef cross_mean
                # Find the mean value crossing points in the last sample_rate filtered samples
#ifdef lowpass
                    for i in range(-(sample_rate) if len(orientation_signal) > sample_rate else -(sample_rate - 1), 0):
                        pass
#else
                    for i in range(-1,0):
                        pass
#endif
                        if ((orientation_signal[i-1]['value'] < mean_signal_value) and (orientation_signal[i]['value'] >= mean_signal_value)) or ((orientation_signal[i-1]['value'] > mean_signal_value) and (orientation_signal[i]['value'] <= mean_signal_value)):
                            mean_crossing_samples.append({'time' : orientation_signal[i]['time'], 'value' : orientation_signal[i]['value'], 'derivative' : orientation_signal[i]['derivative']})
                            if len(mean_crossing_samples) > 1:
                                mean_crossing_samples[-1]['period'] = mean_crossing_samples[-1]['time'] - mean_crossing_samples[-2]['time']
                                
                    if len(mean_crossing_samples) > 0:            
#ifdef period_only
                        calculated_velocity = 1/mean_crossing_samples[-1]['period']
#else
                        calculated_velocity = abs(mean_crossing_samples[-1]['derivative'])/mean_crossing_samples[-1]['period']
#endif
                        stim_leg[0] = -1 if signal_change[-1]['concavity'] == 0 else 1
                        imu_data['velocity'] = str(calculated_velocity) + '|'
#ifdef velocity_print
                        print('Calculated Velocity Zero -', mean_crossing_samples[-1]['derivative'], ' ', mean_crossing_samples[-1]['period'])
#endif
#endif

#ifdef fourier
                fourier_counter = fourier_counter + 1
                if fourier_counter%100 == 0:
                    freq_sample_size = 100
                    selected_samples = [dic['value'] for dic in orientation_signal][-freq_sample_size:]
                    sp = np.fft.fft(selected_samples)
                    freq = np.fft.fftfreq(freq_sample_size, (orientation_signal[-1]['time']-orientation_signal[-freq_sample_size]['time'])/(freq_sample_size-1))
                    main_freq = abs(freq[np.where(sp.imag == np.amax(sp.imag))[0]][0])
#ifdef period_only
                    amplitude = 1
                    calculated_velocity = main_freq
#else
                    amplitude = (max(selected_samples)-min(selected_samples))/2
                    calculated_velocity = main_freq*amplitude
#endif
                    imu_data['velocity'] = str(calculated_velocity) + '|'
#ifdef velocity_print
                    print('Calculated Velocity Fourier -', main_freq, amplitude)
#endif
#endif
                    
                # Keep the size of the arrays below a defined threshold
                if len(orientation_signal) > 1000:
                    del orientation_signal[0:sample_rate]
                
                if len(signal_change) > 200:
                    # If the array is too big and the first elements are deleted, the positions must be updated
                    if last_positive_concavity >= 0:
                        last_positive_concavity = last_positive_concavity - (len(signal_change) - 200)
                    
                    if last_positive_concavity_applied >= 0:
                        last_positive_concavity_applied = last_positive_concavity_applied - (len(signal_change) - 200)
                    
                    if last_negative_concavity >= 0:
                        last_negative_concavity = last_negative_concavity - (len(signal_change) - 200)
                    
                    if last_negative_concavity_applied >= 0:
                        last_negative_concavity_applied = last_negative_concavity_applied - (len(signal_change) - 200)
                    
                    del signal_change[0:(len(signal_change) - 200)]
                
            else:
                print('No velocity to calculate')
            
#ifdef velocity_print
            print(time.time() - thread_start_time, ' - ', queue_data[1], ' ' , calculated_velocity, '\n')
#endif
            '''sleep_time = 0.0041666666666666666666666666666 - (time.time() - thread_start_time) # Runs at 240 Hz max
            if sleep_time > 0:
                time.sleep(sleep_time)'''

        except Exception as e:
                print('Velocity Calculation - Exception raised: ', str(e), ', on line ', str(sys.exc_info()[2].tb_lineno))


def stim_server(address, port, imu_data, stim_leg):
    stim_frequency = 50
    min_vel_stim = 5
    while True:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((address, port))
            s.listen()
            conn, addr = s.accept()
            if s:
                print('Connected to {}'.format(addr))
                source = str(conn.recv(4096))[3:-2]
                print('Source: {}'.format(source))
                if source != 'Stim':
                    continue
            while True:
                loop_start = time.time()
                if s:
                    print(imu_data['velocity'][0:-1], stim_leg[0])
                    if 'velocity' in imu_data and float(imu_data['velocity'][0:-1]) >= min_vel_stim:
                        print('Sent message:',stim_leg[0])
                        out_data = json.dumps(int(stim_leg[0]))
                    else:
                        print('Sent message: 0')
                        out_data = json.dumps(float(0))
                    conn.send(out_data.encode())
                    print(out_data)
                else:
                    print('Disconnected from {}'.format(addr))
                    break
                loop_remaining = 1/stim_frequency - (time.time() - loop_start)
                if loop_remaining > 0:
                    time.sleep(loop_remaining)

        except Exception as e:
            print('Stim - Exception raised: ', str(e), ', on line ', str(sys.exc_info()[2].tb_lineno))
            print('Connection  to {} closed'.format(source))


manager = multiprocessing.Manager()
imu_data = manager.dict()
stim_leg = manager.list(range(1))
# imu_json = multiprocessing.Value()

if __name__ == '__main__':
    # mserver = multiprocessing.Process(target=server, args=('', 50001, imu_data))
    mserver = multiprocessing.Process(target=server, args=('', 50001, t, ang, fes, start_time, running, imu_data))
    # mserver = threading.Thread(target=server, args=(('', 50001),))
    running.value = 1
    mserver.start()

    # sserver = multiprocessing.Process(target=socket_server, args=('', 50002, x, 1))
    # sserver.start()
    # sserver2 = multiprocessing.Process(target=socket_server, args=('', 50003, x, 2))
    # sserver2.start()
    # sserver = multiprocessing.Process(target=socket_server, args=('', 50002, x, 1))
    # sserver.start()
    # sserver2 = multiprocessing.Process(target=socket_server, args=('', 50003, x, 2))
    # sserver2.start()
    sserver3 = multiprocessing.Process(target=vr_server, args=('', 50004, imu_data))
    sserver3.start()
    sserver4 = multiprocessing.Process(target=stim_server, args=('', 50005, imu_data, stim_leg))
    sserver4.start()
    velocity_process = multiprocessing.Process(target=velocity_calculation, args=('', imu_data, stim_leg))
    velocity_process.start()
    # server(('', 50000))

    if real_time_plot:
        if (sys.flags.interactive != 1) or not hasattr(QtCore, 'PYQT_VERSION'):
            QtGui.QApplication.instance().exec_()
    else:
        input('Press ENTER do finish')
    print('Good bye')
    running.value = 0
    mserver.terminate()
    sserver3.terminate()
    sserver4.terminate()
    velocity_process.terminate()
