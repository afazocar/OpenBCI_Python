"""

Core OpenBCI object for handling connections and samples from the board.

EXAMPLE USE:

def handle_sample(sample):
  print(sample.channels)

board = OpenBCIBoard()
board.print_register_settings()
board.start(handle_sample)


"""
import serial
import struct
import numpy as np

SAMPLE_RATE = 250.0  # Hz
START_BYTE = bytes(0xA0)  # start of data packet
END_BYTE = bytes(0xC0)  # end of data packet
ADS1299_Vref = 4.5;  #reference voltage for ADC in ADS1299.  set by its hardware
ADS1299_gain = 24.0;  #assumed gain setting for ADS1299.  set by its Arduino code
scale_fac_uVolts_per_count = ADS1299_Vref/(pow(2,23)-1)/(ADS1299_gain*1000000.);

# command_stop = "s";
# command_startText = "x";
# command_startBinary = "b";
# command_startBinary_wAux = "n";
# command_startBinary_4chan = "v";
# command_activateFilters = "F";
# command_deactivateFilters = "g";
# command_deactivate_channel = {"1", "2", "3", "4", "5", "6", "7", "8"};
# command_activate_channel = {"q", "w", "e", "r", "t", "y", "u", "i"};
# command_activate_leadoffP_channel = {"!", "@", "#", "$", "%", "^", "&", "*"};  //shift + 1-8
# command_deactivate_leadoffP_channel = {"Q", "W", "E", "R", "T", "Y", "U", "I"};   //letters (plus shift) right below 1-8
# command_activate_leadoffN_channel = {"A", "S", "D", "F", "G", "H", "J", "K"}; //letters (plus shift) below the letters below 1-8
# command_deactivate_leadoffN_channel = {"Z", "X", "C", "V", "B", "N", "M", "<"};   //letters (plus shift) below the letters below the letters below 1-8
# command_biasAuto = "`";
# command_biasFixed = "~";

        
class OpenBCIBoard(object):
  """

  Handle a connection to an OpenBCI board.

  Args:
    port: The port to connect to.
    baud: The baud of the serial connection.

  """

  def __init__(self, port=None, baud=115200, filter_data=True):
    if not port:
      port = find_port()
      if not port:
        raise OSError('Cannot find OpenBCI port')
        
    self.ser = serial.Serial(port, baud)
    self.dump_registry_data()
    self.streaming = False
    self.filtering_data = filter_data
    self.channels = 8

    self.read_state = 0;
    # Searching for start(0), sample_count(1),read data(2), read aux(3), search last(4) 

  def printIn(self):
    if not self.streaming:
      # if self.filtering_data:
      #   self.warn('Enabling filter')
      #   self.ser.write('F')
      #   print(self.ser.readline())
        
      # Send an 'b' to the board to tell it to start streaming us text.
      self.ser.write('b')
      # Dump the first line that says "Arduino: Starting..."
      self.streaming = True
    while self.streaming:
      print(struct.unpack('B',self.ser.read())[0]);

  def start(self, callback):
    """

    Start handling streaming data from the board. Call a provided callback
    for every single sample that is processed.

    Args:
      callback: A callback function that will receive a single argument of the
          OpenBCISample object captured.
    
    """
    if not self.streaming:
      # if self.filtering_data:
      #   self.warn('Enabling filter')
      #   self.ser.write('F')
      #   print(self.ser.readline())
        
      # Send an 'b' to the board to tell it to start streaming us text.
      self.ser.write('b')
      # Dump the first line that says "Arduino: Starting..."
      self.ser.readline()
      self.streaming = True
    while self.streaming:
      #data = self.ser.readline()
      sample = self._read_serial_binary()
      callback(sample)

  """

  Turn streaming off without disconnecting from the board

  """
  def stop(self):
    self.streaming = False

  def disconnect(self):
    self.ser.close()
    self.streaming = False

  """ 


      SETTINGS AND HELPERS 


  """

  def dump_registry_data(self):
    """
    
    When starting the connection, dump all the debug data until 
    we get to a line with something about streaming data.
    
    """
    line = ''
    while 'begin streaming data' not in line:
      line = self.ser.readline()  

  def print_register_settings(self):
    self.ser.write('?')
    for number in xrange(0, 24):
      print(self.ser.readline())

  """

  Adds a filter at 60hz to cancel out ambient electrical noise.
  
  """
  def enable_filters(self):
    self.ser.write('f')
    self.filtering_data = True;

  def disable_filters(self):
    self.ser.write('g')
    self.filtering_data = False;

  def warn(self, text):
    print(text)

  def _read_serial_binary(self, max_bytes_to_skip=3000):
    def read(n):
      b = self.ser.read(n)
      # print bytes(b)ar
      return b

    for rep in xrange(max_bytes_to_skip):
      #Looking for start and save id when found
      if self.read_state == 0:
        b = read(1)
        if not b:
          if not self.ser.inWaiting():
              self.warn('Device appears to be stalled. Restarting...')
              self.ser.write('b\n')  # restart if it's stopped...
              time.sleep(.100)
              continue
        if bytes(struct.unpack('B', b)[0]) == START_BYTE:
          if(rep != 0):
            self.warn('Skipped %d bytes before start found' %(rep))
          packet_id = struct.unpack('B', read(1))[0] #packet id goes from 0-255
          
          self.read_state = 1

      #CHECK THIS
      elif self.read_state == 1:
        channel_data = []
        for c in xrange(self.channels):
          #3 byte ints
          literal_read = read(3)

          unpacked = struct.unpack('3B', literal_read)
          #3byte int in 2s compliment
          if (unpacked[0] >= 127): 
            pre_fix = '\xFF'
          else:
            pre_fix = '\x00'
          

          literal_read = pre_fix + literal_read; 

          #unpack little endian(>) signed integer(i)
          #also makes unpacking platform independent
          myInt = struct.unpack('>i', literal_read)

          channel_data.append(myInt[0]*scale_fac_uVolts_per_count)
          
          # # Debug
          # unpacked_final = struct.unpack('4B', literal_read)
          # print unpacked
          # print unpacked_final
          # print myInt 
        
        self.read_state = 2;


      elif self.read_state == 2:
        aux_data = []
        for a in xrange(3):

          #short(h) 
          acc = struct.unpack('h', read(2))[0]
          aux_data.append(acc)
    
        self.read_state = 3;


      elif self.read_state == 3:
        val = bytes(struct.unpack('B', read(1))[0])
        if (val == END_BYTE):
          sample = OpenBCISample(packet_id, channel_data, aux_data)
          self.read_state = 0 #read next packet
          return sample
        else:
          self.warn("Warning: Unexpected END_BYTE found <%s> instead of <%s>,\
            discarted packet with id <%d>" 
            %(val, END_BYTE, packet_id))
  

  def _interprate_stream(self, b):
    print ("interprate")

  def set_channel(self, channel, toggle_position):
    #Commands to set toggle to on position
    if toggle_position == 1: 
      if channel is 1:
        self.ser.write('q')
      if channel is 2:
        self.ser.write('w')
      if channel is 3:
        self.ser.write('e')
      if channel is 4:
        self.ser.write('r')
      if channel is 5:
        self.ser.write('t')
      if channel is 6:
        self.ser.write('y')
      if channel is 7:
        self.ser.write('u')
      if channel is 8:
        self.ser.write('i')
    #Commands to set toggle to off position
    elif toggle_position == 0: 
      if channel is 1:
        self.ser.write('1')
      if channel is 2:
        self.ser.write('2')
      if channel is 3:
        self.ser.write('3')
      if channel is 4:
        self.ser.write('4')
      if channel is 5:
        self.ser.write('5')
      if channel is 6:
        self.ser.write('6')
      if channel is 7:
        self.ser.write('7')
      if channel is 8:
        self.ser.write('8')


class OpenBCISample(object):
  """Object encapulsating a single sample from the OpenBCI board."""
  def __init__(self, packet_id, channel_data, aux_data):
    self.id = packet_id;
    self.channels = channel_data;
    self.aux_data = aux_data;
    

