# pip install spacy
# python -m spacy download en_core_web_sm

import spacy
import logging
import os
import requests
import json

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
                                        "lon": location["x"]
                                        })
            else:
                entity_list.append({
                                    "document": file_name,
                                    "entity_id":e.label, 
                                    "entity_type":e.label_, 
                                    "entity": e.text, 
                                    "spatial_entity": False
                                    })

    return entity_list

def main():
    # Instantiate SpaCy NLP processor
    nlp = spacy.load("en_core_web_sm")

    # Define top level directory
    top_dir = r'/Users/jame9353/Documents/GitHub/SampleData/GulfWarIIRS'
    logging.info('Beginning scan of {}'.format(top_dir))
    print("STARTING")

    # List all files in top level directory
    files_to_process = os.listdir(top_dir)
    logging.info("Found {} files in {}".format(str(len(files_to_process)), top_dir))
    print("Found {} files in {}".format(str(len(files_to_process)), top_dir))

    # Iterate through list of files located in top level directory
    for file in files_to_process:
        filepath = os.path.join(top_dir, file)
        logging.info("Attempting to open {}".format(file))
        print("Attempting to open {}".format(file))
        
        # Ensure that path to file is valid
        if os.path.exists(filepath):
            logging.info("{} is a valid file, processing".format(filepath))
            print("{} is a valid file, processing".format(filepath))
            
            # Open the file in "Read" mode in memory
            with open(filepath, 'r') as text:
                
                try:
                    text_data = text.read().title()
                    nlp_text = (text_data)
                #except UnicodeDecodeError:
                    #logging.error("Unicode Decode Error for {}".format(file))
                except Exception as e:
                    print(e)

                entities = extract_entities(nlp, file, nlp_text)
                print("Found {} entities in {}".format(str(len(entities)), file))

                # Filters to a list of just spatial entities to allow for creation of output feature class
                spatial_entities = list(filter(lambda spatial: spatial['spatial_entity'] == True, entities))
                

if __name__ == "__main__":
    main()