# pip install spacy
# python -m spacy download en_core_web_sm

import spacy
import logging
import os
import requests
import json
import arcpy

def get_head(text, headpos, numchars):
    """Return text before start of entity."""
    wheretostart = headpos - numchars
    if wheretostart < 0:
        wheretostart = 0
    thehead = text[wheretostart: headpos]
    return thehead

def get_tail(text, tailpos, numchars):
    """Return text at end of entity."""
    wheretoend = tailpos + numchars
    if wheretoend > len(text):
        wheretoend = len(text)
    thetail = text[tailpos: wheretoend]
    return thetail

def geocode_address(address):
    """Use World Geocoder to get XY for one address at a time."""
    
    logging.info("Geocoding " + address)
    
    querystring = {
        "f": "json",
        "singleLine": address}
    url = "https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates"
    response = requests.request("GET", url, params=querystring)
    p = response.text
    j = json.loads(p)
    
    try:
        location = j['candidates'][0]['location']  # returns first location as X, Y
        logging.info("Geocoded results: {}".format(str(location)))
            
        return location
    except IndexError:
        logging.error("Index Error on {}".format(address))
        return "IndexError"

def extract_entities(nlp_processor, file_name, text):
    logging.info("Processing {}".format(file_name))
    
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
                
                location = geocode_address(e.text)

                if location != "IndexError":

                    entity_list.append({
                                        "document": file_name,
                                        "entity_id":e.label, 
                                        "entity_type":e.label_, 
                                        "entity": e.text, 
                                        "spatial_entity": True,
                                        "lat": location["y"],
                                        "lon": location["x"],
                                        "pre-text": get_head(text, e.start_char, 255),
                                        "post-text": get_tail(text, e.end_char, 255)
                                        })
            else:
                entity_list.append({
                                    "document": file_name,
                                    "entity_id":e.label, 
                                    "entity_type":e.label_, 
                                    "entity": e.text, 
                                    "spatial_entity": False,
                                    "pre-text": get_head(text, e.start_char, 255),
                                    "post-text": get_tail(text, e.end_char, 255)
                                    })

    return entity_list

def create_fc(out_workspace):

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

def insert_row(output_fc, output_fields, locations_list):
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

def main():
    # Instantiate SpaCy NLP processor
    nlp = spacy.load("en_core_web_sm")

    # Define top level directory
    top_dir = r'C:\Users\jame9353.AVWORLD\Documents\GitHub\SampleData\GulfWarIIRS'
    out_gdb = r'C:\Users\jame9353.AVWORLD\Documents\ArcGIS\Sample\Sample\Sample.gdb'
    arcpy.AddMessage('Beginning scan of {}'.format(top_dir))
    arcpy.AddMessage("STARTING")

    # Create the output feature class and create a list of the fields in the feature class
    # that can be used in the Insert Cursor

    out_fc, out_fields = create_fc(out_gdb)

    # List all files in top level directory
    files_to_process = os.listdir(top_dir)
    arcpy.AddMessage("Found {} files in {}".format(str(len(files_to_process)), top_dir))

    # Iterate through list of files located in top level directory
    for file in files_to_process:
        filepath = os.path.join(top_dir, file)
        arcpy.AddMessage("Attempting to open {}".format(file))
        
        # Ensure that path to file is valid
        if os.path.exists(filepath):
            arcpy.AddMessage("{} is a valid file, processing".format(filepath))
            
            # Open the file in "Read" mode in memory
            with open(filepath, 'r') as text:
                try:
                    text_data = text.read().title()
                    nlp_text = (text_data)
                except UnicodeDecodeError:
                    arcpy.AddError("Unicode Decode Error for {}".format(file))
                except Exception as e:
                    arcpy.AddError(e)

                entities = extract_entities(nlp, file, nlp_text)
                arcpy.AddMessage("Found {} entities in {}".format(str(len(entities)), file))

                # Filters to a list of just spatial entities to allow for creation of output feature class
                spatial_entities = list(filter(lambda spatial: spatial['spatial_entity'] == True, entities))

                arcpy.AddMessage("{} locations were found in {}".format(str(len(spatial_entities)), file))

                # Inserts the spatial entities into the output feature class
                insert_row(out_fc, out_fields, spatial_entities)
                

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        arcpy.AddMessage("User termninated function.")
    finally:
        arcpy.AddMessage("Script successfully completed.")