#!usr/bin/python3
# region Imports -------------------------------------------------------------
from Phidget22.Phidget import *
from Phidget22.Devices.VoltageInput import *
from Phidget22.Devices.DigitalOutput import *
import time
from datetime import datetime, timedelta
import logging
import traceback
# endregion End Imports ------------------------------------------------------

# region Global Variables ----------------------------------------------------
# TODO: Evaluate weather variables should be moved to event routine where used. 
# Input variables
upstreamVoltage = 0.0  # V_u This will be current voltage of upstream pressure transducer
downstreamVoltage = 0.0  # V_d This will be current voltage of downstream pressure transducer
inflationStateTime = datetime.now()  # This variable holds the time when the inflation solenoid was last closed or opened
deflationStateTime = datetime.now()
warningLightTime = datetime.now()

# Calculated variables
upstreamPressure = 0.0  # P_u This will be the calculated upstream pressure in [PSI]
downstreamPressure = 0.0  # P_d This will be the calculated downstream pressure in [PSI]
tankPressure = 0.0  # P_t This will be the calculated tank pressure in [PSI]

# outputs
digitalOutputs = list()

# Constants
SET_PRESSURE = 103.0  # C_1 This is the desired tire pressure
SLOPE_UPSTREAM = 36.674  # C_2 This is the calibration slope for the upstream pressure transducer 
OFFSET_UPSTREAM = -18.4  # C_3 This is the calibration offset for the upstream pressure transducer
SLOPE_DOWNSTREAM = 36.778  # C_4 This is the calibration slope for the downstream pressure transducer
OFFSET_DOWNSTREAM = -18.0  # C_5 This is the calibration offset for the downstream pressure transducer
DEF_OPEN_PRESSURE = SET_PRESSURE + 8  # C_6 This should be a min of C_1+4 and a max of 125 PSI
DEF_CLOSE_PRESSURE = SET_PRESSURE + 5  # C_7 This should be a min of C_1+1 and a max of C_6-1

'''
Since tire pressure is not measured directly, it must be estimated. The tire
pressure during fill is estimated by the equation:
P_t = CORRECTION_CONST1*P_d + CORRECTION_CONST2*P_u + CORRECTION_CONST3
Preliminary testing was done to determine constants for this correction
equation that work well of a verity of circumstances. 
'''
CORRECTION_CONST1 = 1.43
CORRECTION_CONST2 = -0.43
CORRECTION_CONST3 = 0.2

allChannelsAttached = False
# endregion Global Variables -------------------------------------------------

# region Event Handlers ------------------------------------------------------
def onVoltageChange(self: VoltageInput, voltage):
    voltageInput = self
    global upstreamVoltage
    global upstreamPressure
    global downstreamVoltage
    global downstreamPressure
    global tankPressure
    global digitalOutputs
    global inflationStateTime
    global deflationStateTime
    global allChannelsAttached

    # Only process events if both the upstream and downstream sensors are attached
    if allChannelsAttached:
        inflationSolenoid: DigitalOutput = digitalOutputs[0]
        deflationSolenoid: DigitalOutput = digitalOutputs[1]
        warningLight: DigitalOutput = digitalOutputs[2]

        if getPhidgetName(voltageInput) == 'Upstream':
            # Update upstreamVoltage var
            upstreamVoltage = voltage
            # Update upstreamPressure var
            upstreamPressure = voltageToPressure(voltageInput, voltage)
        elif getPhidgetName(voltageInput) == 'Downstream':
                # Update downstreamVoltage var
            downstreamVoltage = voltage
            # Update downstreamPressure var
            downstreamPressure = voltageToPressure(voltageInput, voltage)
        # Update tank
        try:
            if inflationSolenoid.getState():
                tankPressure = CORRECTION_CONST1 * downstreamPressure + \
                    CORRECTION_CONST2 * upstreamPressure + CORRECTION_CONST3
            else:
                tankPressure = downstreamPressure
        except PhidgetException as ex:
            traceback.print_exc()
            msg = "PhidgetException " + str(ex.code) + " (" + ex.description + "): " + ex.details
            print(msg)
            logging.debug(msg)
        
        # Check current stat of all solenoids
        inflationState, deflationState, lightState = False, False, False
        try:
            inflationState = inflationSolenoid.getState()
            deflationState = deflationSolenoid.getState()
            lightState = warningLight.getState()
        except PhidgetException as ex:
            traceback.print_exc()
            msg = "PhidgetException " + str(ex.code) + " (" + ex.description + "): " + ex.details
            print(msg)
            logging.debug(msg)

        # Determine if inflation solenoid should be opened
        inflateNeeded = shouldInflate(\
                        inflationState=inflationState,\
                        inflationChangeTime=inflationStateTime,\
                        upstreamPressure=upstreamPressure,\
                        downstreamPressure=downstreamPressure,\
                        tankPressure=tankPressure
                        )
        solenoidToggle(inflationSolenoid, inflateNeeded)
        
        # TODO: Determine if the deflation solenoid should be opened

        # TODO: Determine if the warning light should be on
        warningLightNeeded = tankPressure < SET_PRESSURE*0.9
        solenoidToggle(warningLight, warningLightNeeded)
        


def onAttach(self):
    name = getPhidgetName(self)
    message = f'The {name} channel has successfully attached'
    print(message)
    logging.debug(message)

def onDetach(self):
    global allChannelsAttached
    allChannelsAttached = False
    name = getPhidgetName(self)
    message = f'The {name} channel has been detached'
    print(message)
    logging.debug(message)
# endregion Event Handlers ---------------------------------------------------

# region Helper Functions ----------------------------------------------------
def voltageToPressure(self: VoltageInput, voltage) -> float:
    if getPhidgetName(self) == 'Upstream':
        return SLOPE_UPSTREAM * voltage + OFFSET_UPSTREAM
    elif getPhidgetName(self) == 'Downstream':
        return SLOPE_DOWNSTREAM * voltage + OFFSET_DOWNSTREAM
    else:
        return 0.00


def getPhidgetName(phidget: Phidget) -> str:
    id =  phidget.getChannel()
    # This method identifies the phidget and returns its name
    if phidget.getHubPort() != 2:
        if phidget.getHubPort() == 0:
            return 'Upstream'
        elif phidget.getHubPort() == 1:
            return 'Downstream'
    else:
        if id == 1:
            return 'Inflation'
        elif id == 2:
            return 'Deflation'
        elif id == 0:
            return 'LED'


def solenoidToggle(do: DigitalOutput, state: bool = None):
    # If no value is given, then just switch the value
    name = getPhidgetName(do)
    if state == None:
        do.setState(not do.getState())
        message = f'Set {name} to {not do.getState()} : [tankPressure = {tankPressure}, \
            upstreamPressure = {upstreamPressure}, downstreamPressure = {downstreamPressure}]'
        print(message)
        logging.debug(message)
    elif do.getState() != state:
        do.setState(state)
        message = f'Set {name} to {state} : [tankPressure = {tankPressure}, \
            upstreamPressure = {upstreamPressure}, downstreamPressure = {downstreamPressure}]'
        print(message)
        logging.debug(message)
        if name == 'Inflation':
            inflationStateTime = datetime.now()
        elif name == 'Deflation':
            deflationStateTime = datetime.now()
        elif name == 'LED':
            warningLightTime = datetime.now()
    else:
        pass


def shouldInflate(inflationState:bool, inflationChangeTime, upstreamPressure:float, downstreamPressure:float, tankPressure:float) -> bool:
    # This method determine if the inflation should be opened
    '''
    For inflation the 
    If not inflating, following conditions must be met to start inflation:
        1) tankPressure is less then SET_PRESSURE - 1psi
        2) Inflation has been closed for more then three seconds
        3) Deflation solenoid is not open --> This can be ignored for now
        4) There is at least 5psi differential across the solenoid (upstreamPressure > downstreamPressure + 5psi)
    Else stop inflating if any of the following:
        1) Inflation has been opened for more than 600 seconds
        2) tankPressure >= SET_PRESSURE
    '''
    if not inflationState:
        condition1 = tankPressure < SET_PRESSURE - 1.0
        condition2 = (datetime.now() - inflationChangeTime).total_seconds() > 3.0
        condition4 = upstreamPressure > downstreamPressure + 5.0
        message = f'Evaluation to start inflation made = condition1:{condition1} and condition2:{condition2} and condition4:{condition4} = {condition1 and condition2 and condition4}'
        print(message)
        return condition1 and condition2 and condition4
    else:
        condition1 = (datetime.now() - inflationChangeTime).total_seconds() > 600.0
        condition2 = tankPressure >= SET_PRESSURE
        message = f'Evaluation to stop inflation made = condition1:{condition1} and condition2:{condition2} = {condition1 and condition2}'
        print(message)
        return not (condition1 or condition2)

def shouldDeflate() -> bool:
    # This method determine if the inflation should be opened
    '''
    For deflation
    If not deflating, the following conditions must be met to start deflation:
        1) tankPressure is greater than DEF_OPEN_PRESSURE
        2) Has been closed for more then 60 seconds
        3) Inflation solenoid is not open  --> This can be ignored for now
        4) Inflation has been closed for more then 60 seconds
    Else stop deflating if:
        1) tankPressure <= DEF_CLOSE_PRESSURE
    '''
    pass

def shouldWarn():
    # This method determine if the inflation should be opened
    pass
# endregion Helper Functions -------------------------------------------------

# region Programing Routines -------------------------------------------------
def main():
    '''This is the main programing loop that runs continually'''
    print('Main program has started')
    logging.info('Program started at: ' + str(datetime.now()))
    
    try:
        # Initiate the Phidgets code object
        viUpstream = VoltageInput()
        viDownstream = VoltageInput()
        doInflation = DigitalOutput()
        doDeflation = DigitalOutput()
        doLight = DigitalOutput()

        # Add outputs to the list of outputs
        digitalOutputs.append(doInflation)
        digitalOutputs.append(doDeflation)
        digitalOutputs.append(doLight)    

        # Set Phidgets addressing parameters
        viUpstream.setHubPort(0)  # Set to VINT port for upstream pressure transducer
        viUpstream.setIsHubPortDevice(True)
        viDownstream.setHubPort(1)  # Set to VINT port for downstream pressure transducer
        viDownstream.setIsHubPortDevice(True)
        doInflation.setHubPort(2)  # Set the VINT port that the relay is connected to
        doInflation.setChannel(1)  # Set the channel on the relay module that the Inflation solenoid is connected to
        doDeflation.setHubPort(2)  # Set the VINT port that the relay is connected to
        doDeflation.setChannel(2)  # Set the channel on the relay module that the Deflation solenoid is connected to
        doLight.setHubPort(2)  # Set the VINT port that the relay is connected to
        doLight.setChannel(0)  # Set the channel on the relay module that the Warning Light is connected to

        # Assign attach/detach handlers
        viDownstream.setOnAttachHandler(onAttach)
        viUpstream.setOnAttachHandler(onAttach)
        doInflation.setOnAttachHandler(onAttach)
        doDeflation.setOnAttachHandler(onAttach)
        doLight.setOnAttachHandler(onAttach)

        viDownstream.setOnDetachHandler(onDetach)
        viUpstream.setOnDetachHandler(onDetach)
        doInflation.setOnDetachHandler(onDetach)
        doDeflation.setOnDetachHandler(onDetach)
        doLight.setOnDetachHandler(onDetach)
        
        # Attach the light 
        doLight.openWaitForAttachment(3000)
        # Flash light to let user know that the program has started
        onTimeSec = 0.05
        offTimeSec = 0.05
        blinkNumber = 10
        for n in range(0,blinkNumber):
            doLight.setState(True)  # Turn on
            time.sleep(onTimeSec)  # Wait on
            doLight.setState(False)  # Turn off
            if n < blinkNumber:
                time.sleep(offTimeSec)  # Wait off


        
        # Assign the event handlers to react to input changes
        viUpstream.setOnVoltageChangeHandler(onVoltageChange)
        viDownstream.setOnVoltageChangeHandler(onVoltageChange)

        # Open channels and wait for attachment
        doDeflation.openWaitForAttachment(3000)
        doInflation.openWaitForAttachment(3000)
        viDownstream.openWaitForAttachment(3000)
        viUpstream.openWaitForAttachment(3000)

        # Set the data sampling interval
        viUpstream.setDataInterval(250)
        viDownstream.setDataInterval(250)
        global allChannelsAttached 
        allChannelsAttached = True

        # Make sure program starts with all solenoids closed 
        solenoidToggle(doDeflation, False)
        solenoidToggle(doInflation, False)
        solenoidToggle(doLight, False)

        # Program will stall here until the Enter key is pressed to close
        try:
            input('Press Enter to Stop\n')
        except (Exception, KeyboardInterrupt):
            pass
    except PhidgetException as ex:
        traceback.print_exc()
        message = "PhidgetException " + str(ex.code) + " (" + ex.description + "): " + ex.details
        print(message)
        logging.debug(message)
    
    doLight.close()
    doDeflation.close()
    doInflation.close()
    viDownstream.close()
    viUpstream.close()
    print('The main program has been exited')
    logging.info('Program ended at: ' + str(datetime.now()))
# endregion Programing Routines ----------------------------------------------

# region for testing ---------------------------------------------------------
def bootTest():
    try:
        print("Boot test started!")
        logging.info('Boot test started at: ' + str(datetime.now()))
        light = DigitalOutput()

        light.setHubPort(2)
        light.setChannel(0)

        light.openWaitForAttachment(3000)
        
        # Flash light to let user know that the program has started
        light.openWaitForAttachment(3000)
        onTimeSec = 0.05
        offTimeSec = 0.05
        blinkNumber = 10
        for n in range(0,blinkNumber):
            light.setState(True)  # Turn on
            time.sleep(onTimeSec)  # Wait on
            light.setState(False)  # Turn off
            if n < blinkNumber:
                time.sleep(offTimeSec)  # Wait off
    except PhidgetException as ex:
        traceback.print_exc()
        message = "PhidgetException " + str(ex.code) + " (" + ex.description + "): " + ex.details
        print(message)
        logging.debug(message)

    print("boot test compleat")
    logging.debug("boot test compleat")

# endregion for testing ------------------------------------------------------


# Program Start Point
'''TODO: add the following line below the to the file /etc/rc.local
    python /root/usr/ECB_road_test_program/ECB Road Test.py
'''
logging.basicConfig(filename='app.log', filemode='a', format='%(name)s - %(levelname)s - %(message)s', level=logging.DEBUG)
# Call the main program
main()
# tm = datetime.now()
# time.sleep(5.0)
# print(shouldInflate(True, tm, 150.0, 100.0, 103.0))
# Program End