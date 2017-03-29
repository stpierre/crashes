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

    injury_region_id = sqlalchemy.Column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("injury_region.id"))
    injury_region = orm.relationship("InjuryRegion")

    injury_severity_id = sqlalchemy.Column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("injury_severity.id"))
    injury_severity = orm.relationship("InjurySeverity")

    location = sqlalchemy.Column(sqlalchemy.String)
    latitude = sqlalchemy.Column(sqlalchemy.Float)
    longitude = sqlalchemy.Column(sqlalchemy.Float)
    geojson = sqlalchemy.Column(sqlalchemy.Text, default="{}")

    hit_and_run = sqlalchemy.Column(sqlalchemy.Boolean)
    hit_and_run_status = sqlalchemy.Column(
        sqlalchemy.Enum("driver", "cyclist", "both", "unknown"))
    dot_code = sqlalchemy.Column(sqlalchemy.Integer)

    road_location_name = sqlalchemy.Column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("location.name"))
    road_location = orm.relationship("Location")

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


class Location(Base):
    __tablename__ = "location"

    fixture = [
        {"name": "crosswalk",
         "desc": ("Collision happened while a person on a bicycle was using a "
                  "crosswalk between two sidewalks; that is, attempting to "
                  "cross a road or intersection either in a painted crosswalk "
                  "that is not part of a bike trail, or crossing an "
                  "intersection from one sidewalk to another. This does not "
                  "include cyclists who are riding on the street and pass "
                  "through the intersection without using a crosswalk, nor "
                  "cyclists in a crosswalk that is part of a bike trail.")},
        {"name": "sidewalk",
         "desc": ("Collision happened while a person on a bicycle was riding "
                  "on a sidewalk that is not a bike trail. For instance, a car "
                  "entering or leaving a private driveway or, in rare "
                  "situations, a car that jumps the curb.")},
        {"name": "bike lane",
         "desc": ("Collision happened while a person on a bicycle was riding "
                  "in a bike lane.")},
        {"name": "bike trail crossing",
         "desc": ("Collision happened while a person on a bicycle was using a "
                  "crosswalk between two bike trail segments, or continuing "
                  "past the end of a bike trail over a crosswalk to the start "
                  "of a sidewalk. This does not include cyclists crossing "
                  "perpendicularly to a bike trail, unless they are continuing "
                  "on another bike trail on the other side.")},
        {"name": "bike trail",
         "desc": ("Collision happened while a person on a bicycle was riding "
                  "on a bike trail, not in an intersection.")},
        {"name": "road",
         "desc": ("Collision happened while a person on a bicycle was riding "
                  "on the road, excluding intersections.")},
        {"name": "intersection",
         "desc": ("Collision happened while a person on a bicycle was riding "
                  "through an intersection on the road, not using a "
                  "crosswalk.")},
        {"name": "elsewhere",
         "desc": ("Collision happened elsewhere (alleyways, parking lots, "
                  "etc.). This also includes ride-outs at mid-block and other "
                  "collisions that happened on the road, but where the cyclist "
                  "was not riding on the road as such.")},
        {"name": "unknown",
         "desc": ("The police report contained insufficient information to "
                  "determine where the collision happened; or the collision "
                  "record came from NDOR and no police report could be "
                  "located.")},
        {"name": "not involved",
         "desc": "No person riding a bicycle was involved in the collision."}]

    name = sqlalchemy.Column(sqlalchemy.String, primary_key=True)
    desc = sqlalchemy.Column(sqlalchemy.Text)
