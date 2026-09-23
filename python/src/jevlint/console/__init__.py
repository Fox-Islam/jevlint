"""The command line: reading the arguments, printing the report, and the exit code."""
from .application import Application, main
from .args import Args
from .flags import Flags
from .output import Output

__all__ = ['Application', 'Args', 'Flags', 'Output', 'main']
