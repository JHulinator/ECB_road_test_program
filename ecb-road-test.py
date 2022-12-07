# region Imports -------------------------------------------------------------
from Phidget22.Phidget import *
from Phidget22.Devices.VoltageInput import *
from Phidget22.Devices.DigitalOutput import *
import time
from datetime import datetime, timedelta
import logging
# endregion End Imports ------------------------------------------------------

# region Global Variables ----------------------------------------------------
# TODO: Evaluate weather variables should be moved to event rutene where used. 
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
SET_PRESSURE = 110.0  # C_1 This is the desired tire pressure
SLOPE_UPSTREAM = 56.694  # C_2 This is the calibration slope for the upstream pressure transducer 
OFFSET_UPSTREAM = -18.0  # C_3 This is the calibration offset for the upstream pressure transducer
SLOPE_DOWNSTREAM = 56.605  # C_4 This is the calibration slope for the downstream pressure transducer
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
# endregion Global Variables -------------------------------------------------

# region Event Handlers ------------------------------------------------------
def onVoltageChange(self: VoltageInput, voltage):
    # Only prosess events if both the upstream and downstream sensors are attached
    voltageInput = self
    global upstreamVoltage
    global upstreamPressure
    global downstreamVoltage
    global downstreamPressure
    global tankPressure
    global digitalOutputs
    global inflationStateTime
    global deflationStateTime

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
    if inflationSolenoid.getState():
        tankPressure = CORRECTION_CONST1 * downstreamPressure + \
            CORRECTION_CONST2 * upstreamPressure + CORRECTION_CONST3
    else:
        tankPressure = downstreamPressure

    # print(f'[upstreamPressure = {upstreamPressure}, downstreamPressure = {downstreamPressure}, tankPressure = {tankPressure}]')
    # Determine if inflation solenoid should be opened
    haveValidPressureValues = upstreamPressure != 0.0 and downstreamPressure != 0.0
    isTankLow = tankPressure < SET_PRESSURE - 1
    stateDuration = (datetime.now() - inflationStateTime)
    isClosedTreeSecounds = (stateDuration.total_seconds() > 3) and not \
        inflationSolenoid.getState()
    isNotOpenedSixHundredSecounds = not ((stateDuration.total_seconds() > 600) \
        and inflationSolenoid.getState())
    isNotDeflating = not deflationSolenoid.getState()
    isSupplyHigher = upstreamPressure > downstreamPressure + 5.0
    # If all of the above conditions are true, then open inflation
    shouldOpenInflation = haveValidPressureValues and isTankLow and \
        isClosedTreeSecounds and isNotOpenedSixHundredSecounds and \
        isNotDeflating and isSupplyHigher and not deflationSolenoid.getState()
    
    # Determine if the deflation solenoid should be opened
    shouldCloseDeflation = tankPressure < DEF_CLOSE_PRESSURE
    isAboveDeflationOpen = tankPressure > DEF_OPEN_PRESSURE
    deflationDuration = (datetime.now() - deflationStateTime)
    isClosedSixtySecounds = (deflationDuration.total_seconds() > 60) and not \
        deflationSolenoid.getState()
    isInflationClosedSixtySecouds = (stateDuration.total_seconds() > 60) and \
        not inflationSolenoid.getState()
    shouldOpenDeflation = isAboveDeflationOpen and isClosedSixtySecounds and \
        isInflationClosedSixtySecouds and not inflationSolenoid.getState()

    # Determine if the warning light should be on
    isPressureLow = tankPressure < SET_PRESSURE * 0.9
    warningLightDuration = (datetime.now() - warningLightTime)
    isOnForSixtySecounds = warningLightDuration.total_seconds() > 60 and \
        warningLight.getState()

    print(f'Invlation? -> {shouldOpenInflation}\n\t\
        hasValidPresure={haveValidPressureValues} \n\t\
        isTankLow={isTankLow}\n\t\
        isClosedTreeSecounds={isClosedTreeSecounds}\n\t\
        isNotOpenedSixHundredSecounds={isNotOpenedSixHundredSecounds}\n\t\
        isNotDeflating={isNotDeflating}\n\t\
        isSupplyHigher={isSupplyHigher}')
    if shouldOpenInflation:
        solinoidToggle(inflationSolenoid, True)
    else:
        solinoidToggle(inflationSolenoid, False)

    if shouldCloseDeflation:
        solinoidToggle(deflationSolenoid, False)
    elif shouldOpenDeflation and not shouldOpenInflation:
        solinoidToggle(deflationSolenoid, True)

    if isPressureLow:
        solinoidToggle(warningLight, True)
    else:
        solinoidToggle(warningLight, False)

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
    # This method identifies the phiget and returns its name
    if phidget.getHubPort() != 2:
        if phidget.getHubPort() == 0:
            return 'Upstream'
        elif phidget.getHubPort() == 1:
            return 'Downstream'
    else:
        if id == 0:
            return 'Inflation'
        elif id == 1:
            return 'Deflation'
        elif id == 2:
            return 'LED'


def solinoidToggle(do: DigitalOutput, state: bool = None):
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

# endregion Helper Functions -------------------------------------------------

# region Programing Routines -------------------------------------------------
def main():
    '''This is the main programing loop that runs continually'''
    print('Main program has started')
    logging.info('Program started at: ' + str(datetime.now()))

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
    doInflation.setChannel(0)  # Set the channel on the relay module that the Inflation solenoid is connected to
    doDeflation.setHubPort(2)  # Set the VINT port that the relay is connected to
    doDeflation.setChannel(1)  # Set the channel on the relay module that the Deflation solenoid is connected to
    doLight.setHubPort(2)  # Set the VINT port that the relay is connected to
    doLight.setChannel(2)  # Set the channel on the relay module that the Warning Light is connected to
    
    print(f'Upstream = [{viUpstream.getHubPort()}, {viUpstream.getChannel()}]\n\
            Downstream = [{viDownstream.getHubPort()}, {viDownstream.getChannel()}]\n\
            Inflation [{doInflation.getHubPort()}, {doInflation.getChannel()}]\n\
            Deflation = [{doDeflation.getHubPort()}, {doDeflation.getChannel()}]\n\
            Light = [{doLight.getHubPort()}, {doLight.getChannel()}]')

    # Flash light to let user know that the program has started
    doLight.openWaitForAttachment(3000)
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

    # Set the data sampeling interval
    viUpstream.setDataInterval(250)
    viDownstream.setDataInterval(250)

    # Make sure program starts with all solinoids closed 
    solinoidToggle(doDeflation, False)
    solinoidToggle(doInflation, False)
    solinoidToggle(doLight, False)

    # Program will stall here until the Enter key is pressed to close
    try:
        input('Press Enter to Stop\n')
    except (Exception, KeyboardInterrupt):
        pass

    doLight.close()
    doDeflation.close()
    doInflation.close()
    viDownstream.close()
    viUpstream.close()
    print('The main program has been exited')
    logging.info('Program endded at: ' + str(datetime.now()))
# endregion Programing Routines ----------------------------------------------

# Program Start Point
'''TODO: add the following line below the to the file /etc/rc.local
    python /root/usr/ECB_road_test_program/ECB Road Test.py
'''
logging.basicConfig(filename='app.log', filemode='w', format='%(name)s - %(levelname)s - %(message)s', level=logging.DEBUG)
# Call the main program
main()
# Program End