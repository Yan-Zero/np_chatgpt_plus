from pydantic import BaseModel, Extra


class Config(BaseModel, extra=Extra.ignore):
    """Plugin Config Here"""
    cw: bool = True
    cw_path: str = 'datastore/cw'