from pydantic import BaseModel, Extra
import os
from typing import List, Optional, Set


class Config(BaseModel, extra=Extra.ignore):
    pass
