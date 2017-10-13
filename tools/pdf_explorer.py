#!/usr/bin/env python
"""Figure out what goes where in an LPD accident report."""

import argparse
import yaml
import os
import sys

from pdfminer import converter as pdfconverter
from pdfminer import layout as pdflayout
from pdfminer import pdfdocument
from pdfminer import pdfinterp
from pdfminer import pdfpage
from pdfminer import pdfparser
from six.moves import input
from six.moves import cPickle as pickle

from crashes.commands import parse


class Coordinates(parse.Coordinates):
    pass


class PDFObject(object):
    def __init__(self,
                 name=None,
                 candidates=None,
                 page_type=None,
                 coordinates=None):
        self.name = name
        self.candidates = candidates or []
        self.page_type = page_type

        if coordinates is None:
            self.coordinates = []
        elif hasattr(coordinates, "__iter__"):
            self.coordinates = coordinates
        else:
            self.coordinates = [coordinates]

    def average_coordinates(self):
        if not self.coordinates:
            raise Exception("No coordinates")
        xmins = xmaxs = ymins = ymaxs = 0.0
        for coords in self.coordinates:
            xmins += coords.xmin
            xmaxs += coords.xmax
            ymins += coords.ymin
            ymaxs += coords.ymax
        return parse.Coordinates(
            xmins / len(self.coordinates), ymins / len(self.coordinates),
            xmaxs / len(self.coordinates), ymaxs / len(self.coordinates))

    def __str__(self):
        return "%s(%s (%s at %s))" % (self.__class__.__name__, self.name
                                      if self.name else self.candidates,
                                      self.page_type,
                                      self.average_coordinates())


class PDFExplorer(object):
    start_index = {
        "report": 345,
        "diagram": 306,
        "40a": 245,
        "addl_diagram": 389,
        "40b": 370,
        "truck_bus": 199,
    }

    start_y = {"diagram": 595, "addl_diagram": 180}

    def __init__(self, statefile=None):
        # objects is a bag of dicts. each dict can have the following keys:
        #
        # * coordinates: list of Coordinates objects giving the different
        #   positions of this object
        # * name: the name of the data in this object
        # * candidates: a list of possible names for this object
        #
        # name and candidates are mutually exclusive
        self.objects = []

        self.statefile = statefile
        if self.statefile and os.path.exists(self.statefile):
            self.objects = pickle.load(open(self.statefile))

    def find_candidate_objects(self, pdfobj, page_type):
        coords = parse.Coordinates(*pdfobj.bbox)
        candidates = []
        for obj in self.objects:
            if obj.name == "skip":
                continue
            if obj.page_type == page_type:
                if any(c.overlaps(coords) for c in obj.coordinates):
                    candidates.append(obj)
        return candidates

    def curate_object(self, pdfobj, page_type):
        print("PDF object at %s" % (pdfobj.bbox, ))
        print("Text content: %s" % parse.get_text(pdfobj))
        coords = parse.Coordinates(*pdfobj.bbox)
        candidates = self.find_candidate_objects(pdfobj, page_type)
        for candidate in candidates:
            if any(c == coords for c in candidate.coordinates):
                candidate.coordinates.append(coords)
                print("Perfect match: %s" % candidate)
                print()
                return

        if candidates:
            print("This object might be:")
            for i, obj in enumerate(candidates):
                print("%s. %s" % (i + 1, obj))

        names = []
        ans = input("Object names, one per line: ").strip()
        if not ans and len(candidates) == 1:
            candidates[0].coordinates.append(coords)
            print()
            return
        elif ans:
            try:
                idx = int(ans)
                candidates[idx - 1].coordinates.append(coords)
                print()
                return
            except ValueError:
                names.append(ans)
            except IndexError:
                print("Invalid selection")
        elif not ans:
            # we don't know what it might be
            print()
            return
        ans = object()
        while ans:
            ans = input().strip()
            if ans:
                names.append(ans)
        if len(names) == 1:
            obj = PDFObject(
                name=names[0], page_type=page_type, coordinates=coords)
        else:
            obj = PDFObject(
                candidates=names, page_type=page_type, coordinates=coords)
        self.objects.append(obj)

    def save_state(self):
        if self.statefile:
            pickle.dump(self.objects, open(self.statefile, "w"))

    def explore(self, filename, start_page=None):
        try:
            start_page = int(start_page)
        except (ValueError, TypeError):
            start_page = 0

        with open(filename, "rb") as stream:
            # so much pdfminer boilerplate....
            document = pdfdocument.PDFDocument(pdfparser.PDFParser(stream))
            rsrcmgr = pdfinterp.PDFResourceManager()
            device = pdfconverter.PDFPageAggregator(
                rsrcmgr, laparams=pdflayout.LAParams())
            interpreter = pdfinterp.PDFPageInterpreter(rsrcmgr, device)

            page_num = 1
            for page in pdfpage.PDFPage.create_pages(document):
                if page_num < start_page:
                    print("Skipping page %s" % page_num)
                    page_num += 1
                    continue

                print("Exploring page %s" % page_num)
                if page_num == 1:
                    page_type = "report"
                elif page_num == 2:
                    page_type = "diagram"
                else:
                    page_type = input(
                        "Page type (%s): " %
                        ", ".join(self.start_index.keys())).strip()

                interpreter.process_page(page)
                layout = device.get_result()

                objects = list(layout)
                idx = self.start_index[page_type]
                for obj in objects[self.start_index[page_type]:]:
                    coords = parse.Coordinates(*obj.bbox)
                    if (page_type in self.start_y
                            and coords.ymin > self.start_y[page_type]):
                        continue
                    print("PDF object at index %s" % idx)
                    self.curate_object(obj, page_type)
                    idx += 1

                    self.save_state()

                page_num += 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action", choices=("list-objects", "delete-object", "explore", "dump"))
    parser.add_argument("--start-page")
    parser.add_argument("arg", nargs="?")
    options = parser.parse_args()

    explorer = PDFExplorer(statefile="explorer.pickle")

    if options.action == "list-objects":
        for obj in explorer.objects:
            if obj.name != "skip":
                print("%s" % obj)
    elif options.action == "delete-object":
        for obj in explorer.objects:
            if obj.name == options.arg:
                explorer.objects.remove(obj)
                explorer.save_state()
    elif options.action == "dump":
        data = {
            "objects": {},
            "skip": {},
            "start_index": explorer.start_index,
            "start_y": explorer.start_y
        }
        for obj in explorer.objects:
            if obj.name == "skip":
                data["skip"].setdefault(obj.page_type, []).extend(
                    list(c) for c in obj.coordinates)
            else:
                data["objects"].setdefault(obj.page_type, {})[obj.name] = {
                    "coordinates": list(obj.average_coordinates())
                }
        print(yaml.dump(data))
    else:
        explorer.explore(options.arg, start_page=options.start_page)


if __name__ == "__main__":
    sys.exit(main())
