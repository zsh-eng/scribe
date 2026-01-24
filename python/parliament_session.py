from typing import List, Dict

class MP:
    def __init__(self, title: str, name: str, constituency: str, appointment: str = ""):
        self.title = title
        self.name = name
        self.constituency = constituency
        self.appointment = appointment

class ParliamentSession:
    def __init__(self, date: str, sitting_no: int, parliament: int, session_no: int, volume_no: int):
        self.date = date
        self.sitting_no = sitting_no
        self.parliament = parliament
        self.session_no = session_no
        self.volume_no = volume_no
        self.present_members = []
        self.absent_members = []

    def set_present_members(self, attendanceList: List[Dict]):
        pass
