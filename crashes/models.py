from sqlalchemy.ext import declarative
import sqlalchemy
from sqlalchemy import orm

Base = declarative.declarative_base()


class Collision(Base):
    __tablename__ = "collision"

    case_no = sqlalchemy.Column(sqlalchemy.String, primary_key=True)

    dob = sqlalchemy.Column(sqlalchemy.Date)
    gender = sqlalchemy.Column(sqlalchemy.Enum("M", "F"))
    initials = sqlalchemy.Column(sqlalchemy.String)

    date = sqlalchemy.Column(sqlalchemy.Date)
    time = sqlalchemy.Column(sqlalchemy.Time)
    report = sqlalchemy.Column(sqlalchemy.Text)

    injury_region = sqlalchemy.Column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("injury_region.id"))
    injury_severity = sqlalchemy.Column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("injury_severity.id"))

    location = sqlalchemy.Column(sqlalchemy.String)
    latitude = sqlalchemy.Column(sqlalchemy.Float)
    longitude = sqlalchemy.Column(sqlalchemy.Float)
    geojson = sqlalchemy.Column(sqlalchemy.Text, default="{}")

    hit_and_run = sqlalchemy.Column(sqlalchemy.Boolean)
    hit_and_run_status = sqlalchemy.Column(
        sqlalchemy.Enum("driver", "cyclist", "both", "unknown"))
    dot_code = sqlalchemy.Column(sqlalchemy.Integer)
    road_location = sqlalchemy.Column(
        sqlalchemy.Enum("crosswalk", "sidewalk",
                        "bike lane", "bike trail", "bike trail crossing",
                        "road", "intersection", "elsewhere", "unknown",
                        "not involved"))

    tickets = orm.relationship("Ticket", back_populates="case")


class Ticket(Base):
    __tablename__ = "ticket"

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True,
                           autoincrement=True)

    case_no = sqlalchemy.Column(sqlalchemy.String,
                                sqlalchemy.ForeignKey("collision.case_no"))
    initials = sqlalchemy.Column(sqlalchemy.String)
    desc = sqlalchemy.Column(sqlalchemy.String)

    case = orm.relationship("Collision", back_populates="tickets")


class InjuryRegion(Base):
    __tablename__ = "injury_region"

    fixture = [{"id": 1, "desc": "Head"},
               {"id": 2, "desc": "Face"},
               {"id": 3, "desc": "Neck"},
               {"id": 4, "desc": "Chest"},
               {"id": 5, "desc": "Back/spine"},
               {"id": 6, "desc": "Shoulder/upper arm"},
               {"id": 7, "desc": "Elbow/lower arm/hand"},
               {"id": 8, "desc": "Abdomen/pelvis"},
               {"id": 9, "desc": "Hip/upper leg"},
               {"id": 10, "desc": "Knee/lower leg/foot"},
               {"id": 11, "desc": "Entire body"},
               {"id": 12, "desc": "Unknown"},
               {"id": 13, "desc": None}]

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True,
                           autoincrement=False)
    desc = sqlalchemy.Column(sqlalchemy.String)


class InjurySeverity(Base):
    __tablename__ = "injury_severity"

    fixture = [{"id": 1, "desc": "Killed"},
               {"id": 2, "desc": "Disabling"},
               {"id": 3, "desc": "Visible but not disabling"},
               {"id": 4, "desc": "Possible but not visible"},
               {"id": 5, "desc": "Uninjured"}]

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True,
                           autoincrement=False)
    desc = sqlalchemy.Column(sqlalchemy.String)
