from datetime import datetime

class SyncManager:
    def __init__(self, app=None):
        self.app = app
        
    def _model_to_dict(self, table_name, record):
        """Converts a model instance to a dictionary, handling specific types."""
        d = {}
        for column in record.__table__.columns:
            val = getattr(record, column.name)
            if isinstance(val, datetime):
                # Use a standard ISO format for comparison/storage
                d[column.name] = val.strftime("%Y-%m-%d %H:%M:%S")
            elif val is None:
                d[column.name] = ""
            else:
                d[column.name] = str(val)
        return d

sync_manager = SyncManager()
