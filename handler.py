import json
import os
import boto3
import uuid
import pprint
import base64
import imghdr


s3client = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")
rekog = boto3.client('rekognition')

bucket = os.getenv("Bucket")
table = dynamodb.Table(os.getenv("Table"))

#class for detecting text in comic
class ComicText:
    def __init__(self, text, postionLeft, postionTop, Widith, Height):
        self.text = text
        self.postionLeft = postionLeft
        self.postionTop = postionTop
        self.Widith = Widith
        self.Height = Height



def list(event, context):
    items = table.scan()["Items"]
    return {
        "body": json.dumps(items),
        "statusCode": 200
    }

def get_public_url(bucket, key):
    return "https://s3.us-east-1.amazonaws.com/{}/{}".format(bucket, key)

def upload(event, context):
    #function to check extesion of uploaded file
    def check_extension(file_extension):
        if file_extension=="png" or file_extension=="jpg" or file_extension=="jpeg" or file_extension=="bmp" :
            return True
        else:
            return False

    #check if there is a body
    if not event['body'] or event['body']=="":
        return {
            "statusCode": 400,
            "body": "empty request"
        }

    #decode body
    try :
        request_body = json.loads(event['body'])
        decoded_body=base64.b64decode(request_body["file"])
    except Exception as e:
        return {
            "statusCode": 500,
            "body": "couldn't decode picture"
        }

    #check extension
    for tf in imghdr.tests:
        extension = tf(decoded_body, None)
        if extension:
            break

    if check_extension(extension):
        #add object to s3
        uid = str(uuid.uuid4()) + "." +extension
        try :
            s3client.put_object(
                Bucket=bucket,
                Key=uid,
                Body=decoded_body,
                ACL="public-read"
            )
        except Exception as e:
            print(e)
            return {
                "statusCode": 500,
                "body": "error ocurred"
            }

        #put item to database
        try:
            table.put_item(Item={
                "ID": uid,
                "FileName": request_body["name"],
                "TextType": "Empty",
                "TextContent": set([""]),
                "URL": get_public_url(bucket, uid)
            })
        except Exception as e:
            print(e)
            return {
                "statusCode": 500,
                "body": "error ocurred"
            }

        body = {
            "url": get_public_url(bucket, uid),
        }

        response = {
            "statusCode": 200,
            "body": json.dumps(body)
        }

        return response

    else:

        response = {
            "statusCode": 400,
            "body": "wrong file type"
        }

        return response


def created(event, context):
    # check if text was comic or not
    def check_text_type(records):
        for i in records:
            if i["Name"] == "Manga":
                return "Manga"
            elif i["Name"] == "Comics":
                return "Comics"

        for i in records:
            if i["Name"] == "Book":
                return "Book"
            elif i["Name"] == "Letter":
                return "Letter"
            elif i["Name"] == "Text":
                return "Text"
            elif i["Name"] == "Poster":
                return "Poster"

        if not records:
            return "Empty"
        else:
            return records[0]

        return records[0]


    def check_labels(label):
        if label == "Book" or label == "Letter" or label == "Text" or label == "Poster" or label == "Manga" or label == "Comics":
            return True
        else:
            return False

    #code starts here
    for j in event["Records"]:
        records = json.loads(j["body"])
        for i in records["Records"]:
            bucket = i["s3"]["bucket"]["name"]
            key = i["s3"]["object"]["key"]
            print(key)

    try:
        resultLabels = rekog.detect_labels(
            Image={
                "S3Object": {
                    "Bucket": bucket,
                    "Name": key
                }
            },
            MaxLabels=3,
            MinConfidence=75
        )
    except Exception as e:
        print(e)
        return False

    #get label
    label = check_text_type(resultLabels["Labels"])

    if check_labels(label):
        print (" is " + label)

        resultText=rekog.detect_text(
        Image={
            "S3Object": {
                "Bucket": bucket,
                "Name": key
            }
        })

        if label == "Manga" or label == "Comics":
            comicDialoguesWords= []
            comicDialoguesSentence = []
            # consts for spacing, usually works well
            TextSpaceX = 0.15
            TextSpaceY=  0.03

            #text detection, adding detected Words as objects to array
            for i in resultText['TextDetections']:
                if i['Type']=="WORD":
                    cd = ComicText(i["DetectedText"], i["Geometry"]["BoundingBox"]["Left"],i["Geometry"]["BoundingBox"]["Top"],i["Geometry"]["BoundingBox"]["Width"],i["Geometry"]["BoundingBox"]["Height"])
                    comicDialoguesWords.append(cd)

            #from detected text group those that are close to each other
            for i in comicDialoguesWords:

                if comicDialoguesSentence == []:
                    comicDialoguesSentence.append(i)
                else:
                    appended = 0
                    for j in comicDialoguesSentence:
                        if j.postionLeft - TextSpaceX-j.Widith <= i.postionLeft and i.postionLeft <= j.postionLeft + TextSpaceX +j.Widith and j.postionTop - TextSpaceY -j.Height <= i.postionTop and i.postionTop <= j.postionTop + TextSpaceY +j.Height:
                            j.text += " " + i.text
                            j.postionLeft = i.postionLeft
                            j.postionTop = i.postionTop
                            j.Widith = i.Widith
                            j.Height = i.Height
                            appended = 1
                            break

                    if appended == 0:
                        comicDialoguesSentence.append(i)


            #add result to database
            table.update_item(
                Key={
                    "ID": key
                },
                UpdateExpression="set TextType = :t",
                ExpressionAttributeValues={
                    ":t": label,
                }
            )

            sentence_text=[]
            for x in comicDialoguesSentence:
                table.update_item(
                    Key={
                        "ID": key
                    },
                    UpdateExpression="ADD TextContent :i",
                    ExpressionAttributeValues={":i": set([x.text])},
                    ReturnValues="UPDATED_NEW"
                )
                sentence_text.append(x.text)

            #if I wanted to sent response about detected text
            json_text_list=json.dumps(sentence_text)
            message = {
                "statusCode": 200,
                "textType": label,
                "text": json_text_list
            }

            return message

        else:

            #if it is just text, detect but don't group it
            wholeText = ""
            for i in resultText['TextDetections']:
                wholeText += i["DetectedText"]
                wholeText += " "

            table.update_item(
                Key={
                    "ID": key
                },
                UpdateExpression="set TextType = :t",
                ExpressionAttributeValues={
                    ":t": label,
                }
            )

            table.update_item(
                Key={
                    "ID": key
                },
                UpdateExpression="ADD TextContent :i",
                ExpressionAttributeValues={":i": set([wholeText])},
                ReturnValues="UPDATED_NEW"
            )

            message  = {
                "statusCode": 200,
                "textType": label,
                "text": wholeText
            }

            return message


    else:
        return False


