"""Exact Nov17 inverse for frozen release snapshots; full current locks are separate."""
from pathlib import Path
import json
R=Path(__file__).resolve().parents[1]
L=json.loads((R/"tests/nov17_maintenance.json").read_text())
def restore_nov17(text,name):
 for p in reversed(L["pages"].get(name,[])):
  if text.count(p["after"])==1:text=text.replace(p["after"],p["before"],1)
  else:assert text.count(p["before"])==1,(name,"unapproved Nov17 maintenance bytes")
 return text
