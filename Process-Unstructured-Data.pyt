# -*- coding: utf-8 -*-

import arcpy
import os
import json
import spacy
import requests

class BaseTool(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "Base Tools"
        self.description = ""

    def validate_workspace(self, input_workspace=None):
        desc = arcpy.Describe(input_workspace)
        if arcpy.Exists(input_workspace) == False:
            return False
        elif desc.dataType != 'Workspace':
            return False
        else:
            return True

    def get_head(self, text=None, headpos=0, numchars=0):
        """Return text before start of entity."""
        wheretostart = headpos - numchars
        if wheretostart < 0:
            wheretostart = 0
        thehead = text[wheretostart: headpos]
        return thehead

    def get_tail(self, text=None, tailpos=0, numchars=0):
        """Return text at end of entity."""
        wheretoend = tailpos + numchars
        if wheretoend > len(text):
            wheretoend = len(text)
        thetail = text[tailpos: wheretoend]
        return thetail

    def geocode_address(self, address):
        """Use World Geocoder to get XY for one address at a time."""
        
        querystring = {
            "f": "json",
            "singleLine": address}
        url = "https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates"
        response = requests.request("GET", url, params=querystring)
        p = response.text
        j = json.loads(p)
        
        try:
            location = j['candidates'][0]['location']  # returns first location as X, Y
                
            return location
        except IndexError:
            return "IndexError"

    def extract_entities(self, nlp_processor, file_name, text):
        
        # Process data with SpaCy
        doc = nlp_processor(text)

        entity_list = []
        
        # Conduct Named Entity Recognition on document
        entities = doc.ents

        # Filter entities to exclude "CARDINAL" entities
        # Cardinal tends to throw a lot more "noise" entities into the list
        for e in entities:
            if e.label_ != 'CARDINAL':
                if e.label_ == 'GPE':

                    # Geocode location
                    
                    location = self.geocode_address(e.text)

                    if location != "IndexError":

                        entity_list.append({
                                            "document": file_name,
                                            "entity_id":e.label, 
                                            "entity_type":e.label_, 
                                            "entity": e.text, 
                                            "spatial_entity": True,
                                            "lat": location["y"],
                                            "lon": location["x"],
                                            "pre-text": self.get_head(text, e.start_char, 255),
                                            "post-text": self.get_tail(text, e.end_char, 255)
                                            })
                else:
                    entity_list.append({
                                        "document": file_name,
                                        "entity_id":e.label, 
                                        "entity_type":e.label_, 
                                        "entity": e.text, 
                                        "spatial_entity": False,
                                        "pre-text": self.get_head(text, e.start_char, 255),
                                        "post-text": self.get_tail(text, e.end_char, 255)
                                        })

        return entity_list

    def create_fc(self, out_workspace):

        desc = arcpy.Describe(out_workspace)
        # Checks to see if the output workspace is a file geodatabase.  If not, returns error and forces
        # user to use a file geodatabase. 
        if desc.dataType != 'Workspace':
            arcpy.AddError('Please select a file geodatabase to output your files.')
            raise ValueError
        # Create output feature class
        arcpy.AddMessage("Creating output feature class in {}".format(out_workspace))

        # Output feature class spatial reference
        sr = arcpy.SpatialReference(4326)

        # Create the Feature Class
        arcpy.CreateFeatureclass_management(out_workspace, "Locations", "POINT", "", "", "", sr)
        out_fc = os.path.join(out_workspace, "Locations")

        arcpy.AddFields_management(out_fc,
                                    [['document', 'TEXT', 'Document', 255, '', ''],
                                    ['entity_id', 'TEXT', 'Entity Id', 255, '', ''],
                                    ['entity_type', 'TEXT', 'Entity Type', 255, '', ''],
                                    ['extracted_value', 'TEXT', 'Extracted Value', 255, '', ''], 
                                    ['pre_text', 'TEXT', 'Pre-Text', 255, '', ''],
                                    ['post_text', 'TEXT', 'Post-Text', 255, '', ''],
                                    ['lon', 'FLOAT'],
                                    ['lat', 'FLOAT'],])

        fields = ["SHAPE@XY", 'document', 'entity_id', "entity_type", "extracted_value", "pre_text", "post_text", "lon", "lat"]

        return out_fc, fields

    def insert_row(self, output_fc, output_fields, locations_list):
        with arcpy.da.InsertCursor(output_fc, output_fields) as cursor:
            for location in locations_list:
                row = [(location["lon"], location["lat"]),
                        location["document"],
                        location["entity_id"],
                        location["entity_type"],
                        location["entity"],
                        location["pre-text"],
                        location["post-text"],
                        location["lon"],
                        location["lat"]]

                cursor.insertRow(row)
        arcpy.AddMessage("Successfully inserted locations into output feature class")

    def process_text(self, nlp_processor=None, text=None, document=None, output_fc=None, output_fields=None):
        arcpy.AddMessage('Beginning scan of {}'.format(document))

        try:
            nlp_text = (text)
            entities = self.extract_entities(nlp_processor, document, nlp_text)
            arcpy.AddMessage("Found {} entities in {}".format(str(len(entities)), document))

            # Filters to a list of just spatial entities to allow for creation of output feature class
            spatial_entities = list(filter(lambda spatial: spatial['spatial_entity'] == True, entities))

            arcpy.AddMessage("{} locations were found in {}".format(str(len(spatial_entities)), document))

            # Inserts the spatial entities into the output feature class
            self.insert_row(output_fc, output_fields, spatial_entities)
        except UnicodeDecodeError:
            arcpy.AddError("Unicode Decode Error for {}".format(document))
        except Exception as e:
            arcpy.AddError(e)


class Toolbox(object):
    def __init__(self):
        """Define the toolbox (the name of the toolbox is the name of the
        .pyt file)."""
        self.label = "Toolbox"
        self.alias = ""

        # List of tool classes associated with this toolbox
        self.tools = [ExtractLocations]


class ExtractLocations(BaseTool):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "Find Placenames in Text"
        self.description = ""
        self.canRunInBackground = False

    def getParameterInfo(self):
        """Define parameter definitions"""

        input_files = arcpy.Parameter(
            displayName="Files to Process",
            name="input_files",
            datatype="DEFile",
            parameterType="Required",
            direction="Input",
            multiValue=True
        )

        output_workspace = arcpy.Parameter(
            name="out_ws",
            displayName="Output Workspace",
            direction="Input",
            datatype="DEWorkspace",
            parameterType="Required"
        )

        params = [input_files, output_workspace]
        return params

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        return

    def execute(self, parameters, messages):
        """The source code of the tool."""
        input_documents = parameters[0].valueAsText
        output_workspace = parameters[1].valueAsText

        individual_files = input_documents.split(";")
        
        nlp = spacy.load("en_core_web_sm")

        # Validates the output workspace.  If valid, allows the processing to continue.
        # This checks that the output workspace is set to a Geodatabase.
        if self.validate_workspace(output_workspace):
            # Create the output feature class and create a list of the fields in the feature class
            # that can be used in the Insert Cursor
            out_fc, out_fields = self.create_fc(output_workspace)

            for document in individual_files:
                if os.path.exists(document):
                    file_name = os.path.split(document)[1]
                    file_ext = os.path.splitext(document)[1]
                    if file_ext == '.txt':
                        try:
                            with open(document, 'r') as text:
                                lines = text.read()
                                self.process_text(nlp, lines, document, out_fc, out_fields)
                        except IOError:
                            arcpy.AddMessage(file_name + " is not accessible")

                    else:
                        arcpy.AddError(file_ext + " is not a supported file extension.")
                        arcpy.AddError("Please limit data to text files.")
        
        return
