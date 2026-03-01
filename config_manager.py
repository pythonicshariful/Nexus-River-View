import os
import json

def get_profiles_config_path(data_dir):
    return os.path.join(data_dir, 'profiles.json')

def load_profiles(data_dir):
    config_path = get_profiles_config_path(data_dir)
    default_config = {
        "active_profile": "default",
        "profiles": {
            "default": {
                "name": "Nexus River View",
                "db_name": "nexus.db",
                "sheet_id": "1Uapf1c4wDZ4hGfa1bqSbRjF45VodFv2-jtzgLL4VDq0"
            }
        }
    }
    
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                
            # Quick validation
            if 'active_profile' not in config or 'profiles' not in config:
                return default_config
                
            # If the active profile doesn't exist in the loaded profiles, fallback to the first available or default
            if config['active_profile'] not in config['profiles']:
                if config['profiles']:
                    config['active_profile'] = list(config['profiles'].keys())[0]
                else:
                    return default_config
                    
            return config
        except Exception as e:
            print(f"Error loading profiles: {e}")
            return default_config
    else:
        # Create default profiles.json
        save_profiles(data_dir, default_config)
        return default_config

def save_profiles(data_dir, config):
    config_path = get_profiles_config_path(data_dir)
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4)
        return True
    except Exception as e:
        print(f"Error saving profiles: {e}")
        return False
        
def get_active_profile(data_dir):
    config = load_profiles(data_dir)
    active_key = config['active_profile']
    return active_key, config['profiles'][active_key]
