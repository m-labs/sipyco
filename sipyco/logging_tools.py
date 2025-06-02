import warnings
from sipyco.logs import *

warnings.warn("The 'sipyco.logging_tools' module is deprecated. "
              "Please use 'sipyco.logs' instead.",
              DeprecationWarning, stacklevel=2)
