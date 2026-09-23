import sys
import json

if __name__ == '__main__':
    skill_id = sys.argv[1] if len(sys.argv) > 1 else 'emotional_logistics_mapping'
    try:
        from modules.self_evolution.skill_manager import get_skill_manager
        mgr = get_skill_manager()
        skill = mgr.approve_skill(skill_id)
        print(json.dumps(skill, indent=2, ensure_ascii=False))
    except Exception as e:
        print('ERROR:', str(e))
        sys.exit(1)
