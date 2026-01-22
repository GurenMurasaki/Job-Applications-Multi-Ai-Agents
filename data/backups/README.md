# Backups Directory

This folder contains automatic backups of your profile files created by the Profile Updater Agent.

Each backup is stored in a timestamped folder (e.g., `20260122_153045/`) containing:
- `user_profile.yaml`
- `experience.md`
- `motivations.md`

To restore a previous profile:
```bash
cp data/backups/TIMESTAMP/user_profile.yaml config/
cp data/backups/TIMESTAMP/experience.md data/user/
cp data/backups/TIMESTAMP/motivations.md data/user/
```
