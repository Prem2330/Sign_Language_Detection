#!/usr/bin/env python
# -*- coding: utf-8 -*-
import csv  # Parsing through CSV file
import copy  # Creating duplicate objects
import argparse  # Parse command line arguments
import itertools  # Used for looping
import pywhatkit
import time
from transformers import pipeline
from flask_cors import CORS
from googletrans import Translator
import google.generativeai as genai   # pip install -q -U google-generativeai
import re
import cv2 as cv  # Computer Vision library for face detection, object detection , camera and more
import numpy as np  # Create arrays for scientific computing
import mediapipe as mp  # used for hand tracking, object detection , pose, etc
from urllib.parse import quote

from utils import CvFpsCalc  # Used for calculating frame rates etc
from model import KeyPointClassifier  # work with keypoints
from gtts import gTTS
from mtranslate import translate
import pywhatkit as kit
from flask import Flask, render_template, Response, jsonify, request,send_from_directory




app = Flask(__name__)
CORS(app)

API_KEY = 'AIzaSyCWSTzDbV4y9M5iSiVPlbYWBq4djZ-p3Sg'
genai.configure(api_key=API_KEY)
model = genai.GenerativeModel('gemini-pro')

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/video_feed')
def video_feed():
    return Response(main(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/Static/<path:filename>')
def serve_static(filename):
    return send_from_directory('Static', filename)


def get_args():
    parser = argparse.ArgumentParser()

    parser.add_argument("--device", type=int, default=0)
    parser.add_argument("--width", help='cap width', type=int, default=960)
    parser.add_argument("--height", help='cap height', type=int, default=540)

    parser.add_argument('--use_static_image_mode', action='store_true')
    parser.add_argument("--min_detection_confidence",
                        help='min_detection_confidence',
                        type=float,
                        default=0.7)
    parser.add_argument("--min_tracking_confidence",
                        help='min_tracking_confidence',
                        type=int,
                        default=0.5)

    args, unknown = parser.parse_known_args()

    return args


text = ""
signal=0
recommendation_done=0



# This function gives the information of the device which helps in setting up the camera,etc

def main():
    textarr = []
    # Argument parsing #################################################################
    args = get_args()
    cap_device = 0  # Default to the first camera device (assuming a webcam)
    cap_width = 640  # Default width for capturing frames
    cap_height = 480  # Default height for capturing frames
    use_static_image_mode = False  # Default to not using static image mode
    min_detection_confidence = 0.5  # Default minimum confidence for detection
    min_tracking_confidence = 0.5  # Default minimum confidence for tracking

    use_brect = True

    # Camera preparation ###############################################################
    cap = cv.VideoCapture(cap_device)
    cap.set(cv.CAP_PROP_FRAME_WIDTH, cap_width)
    cap.set(cv.CAP_PROP_FRAME_HEIGHT, cap_height)

    # Model load #############################################################
    mp_hands = mp.solutions.hands  # import hands module
    hands = mp_hands.Hands(
        static_image_mode=use_static_image_mode,  # 1=Image,2=Video
        max_num_hands=2,
        min_detection_confidence=min_detection_confidence,  # Min score for hand to be valid
        min_tracking_confidence=min_tracking_confidence,  # Max score for hand to be valid
    )

    keypoint_classifier = KeyPointClassifier()

    # Read labels ###########################################################
    with open('model/keypoint_classifier/keypoint_classifier_label.csv',
              encoding='utf-8-sig') as f:
        keypoint_classifier_labels = csv.reader(f)
        keypoint_classifier_labels = [
            row[0] for row in keypoint_classifier_labels  # First value taken in each row of csv file
        ]

    # FPS Measurement ########################################################
    cvFpsCalc = CvFpsCalc(buffer_len=10)  # FPS tells us how fast our program is running

    # Coordinate history #################################################################

    #  ########################################################################
    mode = 0
    # print("Sentence Recommendation")
    sentence_arr = []
    while True:
        fps = cvFpsCalc.get()

        # Process Key (ESC: end) #################################################
        key = cv.waitKey(10)
        if key == 27:  # ESC
            break
        number, mode = select_mode(key, mode)  # Assign different modes on button clicks

        # Camera capture #####################################################
        ret, image = cap.read()
        if not ret:
            break
        image = cv.flip(image, 1)  # Mirror display
        debug_image = copy.deepcopy(image)

        # Detection implementation #############################################################
        image = cv.cvtColor(image, cv.COLOR_BGR2RGB)  # Ensure compatibility with others

        image.flags.writeable = False  # For data intigrity
        results = hands.process(image)  # Detects hands
        image.flags.writeable = True

        position = (50, 50)  # (x, y) coordinates where the text will be placed
        font = cv.FONT_HERSHEY_SIMPLEX
        font_scale = 1
        color = (255, 0, 0)  # Text color in BGR format
        thickness = 2  # Thickness of the text
        #  ####################################################################
        if results.multi_hand_landmarks is not None:
            for hand_landmarks, handedness in zip(results.multi_hand_landmarks,
                                                  results.multi_handedness):
                # Bounding box calculation
                brect = calc_bounding_rect(debug_image, hand_landmarks)
                # Landmark calculation
                landmark_list = calc_landmark_list(debug_image, hand_landmarks)

                # Conversion to relative coordinates / normalized coordinates
                pre_processed_landmark_list = pre_process_landmark(
                    landmark_list)
                # Write to the dataset file
                logging_csv(number, mode, pre_processed_landmark_list)

                # Hand sign classification
                hand_sign_id = keypoint_classifier(pre_processed_landmark_list)
                # print(hand_sign_id)

                # Add the text to the image

                debug_image = draw_bounding_rect(use_brect, debug_image, brect)
                debug_image = draw_landmarks(debug_image, landmark_list)

                debug_image, hand_sign_text = draw_info_text(
                    debug_image,
                    brect,
                    handedness,
                    keypoint_classifier_labels[hand_sign_id]
                )
                if hand_sign_text not in textarr:
                    if (hand_sign_text == "No"):
                        global signal
                        signal=1
                    elif (hand_sign_text == "Yes"):
                        signal = 2
                    elif (hand_sign_text == "Message"):
                        signal = 3
                    else:
                        textarr.append(hand_sign_text)


        global text

        sentence = " ".join(textarr)
        text = str(sentence)
        debug_image = cv.putText(debug_image, text, (50, 50), cv.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        debug_image = draw_info(debug_image, fps, mode, number)

        x = 50
        for i in range(len(sentence_arr)):
            x = x + 100
            debug_image = cv.putText(debug_image, sentence_arr[i], (50, x), cv.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255),
                                     2)

        key = cv.waitKey(10)
        if key == 49:
            # print(sentence_arr[0])

            debug_image = cv.putText(debug_image, text, (50, 50), cv.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)


        if key == 50:
            pass
            # print(sentence_arr[1])
        if key == 51:
            pass
            # print(sentence_arr[2])

        key = cv.waitKey(10)
        if key == 13:  # Press ESC again to close the window completely
            sentence_arr = enter_ispressed()
            sentences = " ".join(sentence_arr)
            sentences = str(sentences)
            # print(sentences)
            print(sentences)

        key = cv.waitKey(10)
        if key == 112:
            textarr.pop()
            # print(textarr)

        # Screen reflection #############################################################
        # cv.imshow('Hand Gesture Recognition', debug_image)
        ret, buffer = cv.imencode('.jpg', debug_image)
        frame_bytes = buffer.tobytes()

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
    #
    # cap.release()
    # cv.destroyAllWindows()
    # print(textarr)


def translate_text(text, target_language):
    translator = Translator()
    translation = translator.translate(text, dest=target_language)
    return translation.text


@app.route('/translate', methods=['POST'])
def translatesentence():
    data=request.get_json()
    sentence=data['sentence']
    hindi_text = translate_text(sentence,'hi')
    tts = gTTS(text=hindi_text, lang="en")
    tts.save("./Static/output_audio.mp3")
    return jsonify({'message': hindi_text})


@app.route('/NoEncountered', methods=['POST'])
def Yesnoencountered():
    global signal
    if signal == 1:
        signal=0;
        return jsonify({'message': "No encountered"})
    elif signal == 2:
        signal = 0;
        return jsonify({'message': "Yes encountered"})
    elif signal == 3 and recommendation_done==1:
        signal = 0;
        return jsonify({'message': "Send message"})
    else:
        return jsonify({'message':"Not encountered"})


@app.route('/recommendation', methods=['POST'])
def enter_ispressed():
    global recommendation_done
    recommendation_done = 1
    global text
    prompt = f"Write 3 different grammatically correct and simple short sentences that contain with the following words without numbering:: '{text}'"
    response = model.generate_content(prompt)
    sentences = response.text
    sentences_array = sentences.split('\n')
    sentences_array = [sentence.strip() for sentence in sentences_array if sentence.strip()]
    result = sentences_array
    return jsonify({'result': result})


@app.route('/whatsapp', methods=['POST'])
def sendmsg():
    data = request.get_json()
    message = data['sentence']
    phone_number = "+919021069704"  # Phone number as a string
    encoded_message = quote(message.encode('utf-8'))  # Encode message to bytes and then quote
    pywhatkit.sendwhatmsg_instantly(phone_number, message)
    global signal
    signal=0
    return jsonify({'message': 'Message sent successfully'})






# @app.route('/recommendation', methods=['POST'])
# def enter_ispressed():
#     global text
#     prompt = f"Write 3 different grammatically correct and simple sentences that contain with the following words: '{text}'"
#     response = model.generate_content(prompt)
#     sentences = response.text
#     return sentences
#     global recommendation_done
#     recommendation_done=1
#     global text
#
#     prompt = f"Write 3 different grammatically correct and simple sentences that contain with the following words: '{text}'"
#     response = model.generate_content(prompt)
#     sentences = response.text
#     # text_generator = pipeline("text-generation", model="gpt2")
#     # global text
#     # data = text
#     # prefix = data
#     # sentence_Arr = []
#     # max_length = 30
#     # completions = text_generator(prefix, max_length=max_length, num_return_sequences=3)
#     # if completions:
#     #     print("Auto-complete suggestions:")
#     #     for i, completion in enumerate(completions, 1):
#     #         generated_text = completion['generated_text']
#     #         # Filter out incomplete sentences
#     #         sentences = re.split(r"(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<=\.|\?|\!)\s", generated_text)
#     #         complete_sentences = [sentence for sentence in sentences if
#     #                               len(sentence.strip()) > 0 and len(sentence.split()) >= 3]
#     #         if complete_sentences:
#     #             print(f"{i}. {complete_sentences[0]}")
#     #             sentence_Arr.append(complete_sentences[0])
#     #         else:
#     #             print(f"{i}. (Incomplete or nonsensical)")
#     # else:
#     #     print("No suggestions found.")
#
#
#

def select_mode(key, mode):
    number = -1

    if key == 110:  # n
        mode = 0
    if key == 107:  # k
        mode = 1

    if mode == 1:
        num = 0  # this will vary from [0-90] to achive double-digit indexing
        number = num + (key - 48)

    return number, mode


def calc_bounding_rect(image, landmarks):
    image_width, image_height = image.shape[1], image.shape[0]

    landmark_array = np.empty((0, 2), int)

    for _, landmark in enumerate(landmarks.landmark):
        landmark_x = min(int(landmark.x * image_width), image_width - 1)
        landmark_y = min(int(landmark.y * image_height), image_height - 1)

        landmark_point = [np.array((landmark_x, landmark_y))]

        landmark_array = np.append(landmark_array, landmark_point, axis=0)

    x, y, w, h = cv.boundingRect(landmark_array)

    return [x, y, x + w, y + h]


def calc_landmark_list(image, landmarks):
    image_width, image_height = image.shape[1], image.shape[0]

    landmark_point = []

    # Keypoint
    for _, landmark in enumerate(landmarks.landmark):
        landmark_x = min(int(landmark.x * image_width), image_width - 1)
        landmark_y = min(int(landmark.y * image_height), image_height - 1)
        # landmark_z = landmark.z

        landmark_point.append([landmark_x, landmark_y])

    return landmark_point


def pre_process_landmark(landmark_list):
    temp_landmark_list = copy.deepcopy(landmark_list)

    # Convert to relative coordinates
    base_x, base_y = 0, 0
    for index, landmark_point in enumerate(temp_landmark_list):
        if index == 0:
            base_x, base_y = landmark_point[0], landmark_point[1]

        temp_landmark_list[index][0] = temp_landmark_list[index][0] - base_x
        temp_landmark_list[index][1] = temp_landmark_list[index][1] - base_y

    # Convert to a one-dimensional list
    temp_landmark_list = list(
        itertools.chain.from_iterable(temp_landmark_list))

    # Normalization
    max_value = max(list(map(abs, temp_landmark_list)))

    def normalize_(n):
        return n / max_value

    temp_landmark_list = list(map(normalize_, temp_landmark_list))

    return temp_landmark_list


def logging_csv(number, mode, landmark_list):
    if mode == 0:
        pass
    if mode == 1 and (0 <= number <= 99):
        csv_path = '.venv/lib/python3.8/model/keypoint_classifier/keypoint.csv'
        with open(csv_path, 'a', newline="") as f:
            writer = csv.writer(f)
            writer.writerow([number, *landmark_list])
    return


def draw_landmarks(image, landmark_point):
    if len(landmark_point) > 0:
        # Thumb
        cv.line(image, tuple(landmark_point[2]), tuple(landmark_point[3]),
                (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[2]), tuple(landmark_point[3]),
                (255, 255, 255), 2)
        cv.line(image, tuple(landmark_point[3]), tuple(landmark_point[4]),
                (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[3]), tuple(landmark_point[4]),
                (255, 255, 255), 2)

        # Index finger
        cv.line(image, tuple(landmark_point[5]), tuple(landmark_point[6]),
                (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[5]), tuple(landmark_point[6]),
                (255, 255, 255), 2)
        cv.line(image, tuple(landmark_point[6]), tuple(landmark_point[7]),
                (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[6]), tuple(landmark_point[7]),
                (255, 255, 255), 2)
        cv.line(image, tuple(landmark_point[7]), tuple(landmark_point[8]),
                (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[7]), tuple(landmark_point[8]),
                (255, 255, 255), 2)

        # Middle finger
        cv.line(image, tuple(landmark_point[9]), tuple(landmark_point[10]),
                (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[9]), tuple(landmark_point[10]),
                (255, 255, 255), 2)
        cv.line(image, tuple(landmark_point[10]), tuple(landmark_point[11]),
                (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[10]), tuple(landmark_point[11]),
                (255, 255, 255), 2)
        cv.line(image, tuple(landmark_point[11]), tuple(landmark_point[12]),
                (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[11]), tuple(landmark_point[12]),
                (255, 255, 255), 2)

        # Ring finger
        cv.line(image, tuple(landmark_point[13]), tuple(landmark_point[14]),
                (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[13]), tuple(landmark_point[14]),
                (255, 255, 255), 2)
        cv.line(image, tuple(landmark_point[14]), tuple(landmark_point[15]),
                (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[14]), tuple(landmark_point[15]),
                (255, 255, 255), 2)
        cv.line(image, tuple(landmark_point[15]), tuple(landmark_point[16]),
                (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[15]), tuple(landmark_point[16]),
                (255, 255, 255), 2)

        # Little finger
        cv.line(image, tuple(landmark_point[17]), tuple(landmark_point[18]),
                (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[17]), tuple(landmark_point[18]),
                (255, 255, 255), 2)
        cv.line(image, tuple(landmark_point[18]), tuple(landmark_point[19]),
                (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[18]), tuple(landmark_point[19]),
                (255, 255, 255), 2)
        cv.line(image, tuple(landmark_point[19]), tuple(landmark_point[20]),
                (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[19]), tuple(landmark_point[20]),
                (255, 255, 255), 2)

        # Palm
        cv.line(image, tuple(landmark_point[0]), tuple(landmark_point[1]),
                (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[0]), tuple(landmark_point[1]),
                (255, 255, 255), 2)
        cv.line(image, tuple(landmark_point[1]), tuple(landmark_point[2]),
                (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[1]), tuple(landmark_point[2]),
                (255, 255, 255), 2)
        cv.line(image, tuple(landmark_point[2]), tuple(landmark_point[5]),
                (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[2]), tuple(landmark_point[5]),
                (255, 255, 255), 2)
        cv.line(image, tuple(landmark_point[5]), tuple(landmark_point[9]),
                (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[5]), tuple(landmark_point[9]),
                (255, 255, 255), 2)
        cv.line(image, tuple(landmark_point[9]), tuple(landmark_point[13]),
                (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[9]), tuple(landmark_point[13]),
                (255, 255, 255), 2)
        cv.line(image, tuple(landmark_point[13]), tuple(landmark_point[17]),
                (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[13]), tuple(landmark_point[17]),
                (255, 255, 255), 2)
        cv.line(image, tuple(landmark_point[17]), tuple(landmark_point[0]),
                (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[17]), tuple(landmark_point[0]),
                (255, 255, 255), 2)

    # Key Points
    for index, landmark in enumerate(landmark_point):
        if index == 0:
            cv.circle(image, (landmark[0], landmark[1]), 5, (255, 255, 255),
                      -1)
            cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 0), 1)
        if index == 1:
            cv.circle(image, (landmark[0], landmark[1]), 5, (255, 255, 255),
                      -1)
            cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 0), 1)
        if index == 2:
            cv.circle(image, (landmark[0], landmark[1]), 5, (255, 255, 255),
                      -1)
            cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 0), 1)
        if index == 3:
            cv.circle(image, (landmark[0], landmark[1]), 5, (255, 255, 255),
                      -1)
            cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 0), 1)
        if index == 4:
            cv.circle(image, (landmark[0], landmark[1]), 8, (255, 255, 255),
                      -1)
            cv.circle(image, (landmark[0], landmark[1]), 8, (0, 0, 0), 1)
        if index == 5:
            cv.circle(image, (landmark[0], landmark[1]), 5, (255, 255, 255),
                      -1)
            cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 0), 1)
        if index == 6:
            cv.circle(image, (landmark[0], landmark[1]), 5, (255, 255, 255),
                      -1)
            cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 0), 1)
        if index == 7:
            cv.circle(image, (landmark[0], landmark[1]), 5, (255, 255, 255),
                      -1)
            cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 0), 1)
        if index == 8:
            cv.circle(image, (landmark[0], landmark[1]), 8, (255, 255, 255),
                      -1)
            cv.circle(image, (landmark[0], landmark[1]), 8, (0, 0, 0), 1)
        if index == 9:
            cv.circle(image, (landmark[0], landmark[1]), 5, (255, 255, 255),
                      -1)
            cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 0), 1)
        if index == 10:
            cv.circle(image, (landmark[0], landmark[1]), 5, (255, 255, 255),
                      -1)
            cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 0), 1)
        if index == 11:
            cv.circle(image, (landmark[0], landmark[1]), 5, (255, 255, 255),
                      -1)
            cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 0), 1)
        if index == 12:
            cv.circle(image, (landmark[0], landmark[1]), 8, (255, 255, 255),
                      -1)
            cv.circle(image, (landmark[0], landmark[1]), 8, (0, 0, 0), 1)
        if index == 13:
            cv.circle(image, (landmark[0], landmark[1]), 5, (255, 255, 255),
                      -1)
            cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 0), 1)
        if index == 14:
            cv.circle(image, (landmark[0], landmark[1]), 5, (255, 255, 255),
                      -1)
            cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 0), 1)
        if index == 15:
            cv.circle(image, (landmark[0], landmark[1]), 5, (255, 255, 255),
                      -1)
            cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 0), 1)
        if index == 16:
            cv.circle(image, (landmark[0], landmark[1]), 8, (255, 255, 255),
                      -1)
            cv.circle(image, (landmark[0], landmark[1]), 8, (0, 0, 0), 1)
        if index == 17:
            cv.circle(image, (landmark[0], landmark[1]), 5, (255, 255, 255),
                      -1)
            cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 0), 1)
        if index == 18:
            cv.circle(image, (landmark[0], landmark[1]), 5, (255, 255, 255),
                      -1)
            cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 0), 1)
        if index == 19:
            cv.circle(image, (landmark[0], landmark[1]), 5, (255, 255, 255),
                      -1)
            cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 0), 1)
        if index == 20:
            cv.circle(image, (landmark[0], landmark[1]), 8, (255, 255, 255),
                      -1)
            cv.circle(image, (landmark[0], landmark[1]), 8, (0, 0, 0), 1)

    return image


def draw_bounding_rect(use_brect, image, brect):
    if use_brect:
        # Outer rectangle
        cv.rectangle(image, (brect[0], brect[1]), (brect[2], brect[3]),
                     (0, 0, 0), 1)

    return image


def draw_info_text(image, brect, handedness, hand_sign_text):
    cv.rectangle(image, (brect[0], brect[1]), (brect[2], brect[1] - 22),
                 (0, 0, 0), -1)

    info_text = handedness.classification[0].label[0:]
    if hand_sign_text != "":
        info_text = info_text + ':' + hand_sign_text
    cv.putText(image, info_text, (brect[0] + 5, brect[1] - 4),
               cv.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv.LINE_AA)

    return image, hand_sign_text


def draw_info(image, fps, mode, number):
    cv.putText(image, "FPS:" + str(fps), (10, 30), cv.FONT_HERSHEY_SIMPLEX,
               1.0, (0, 0, 0), 4, cv.LINE_AA)
    cv.putText(image, "FPS:" + str(fps), (10, 30), cv.FONT_HERSHEY_SIMPLEX,
               1.0, (255, 255, 255), 2, cv.LINE_AA)

    mode_string = ['Logging Key Point']
    if 1 <= mode <= 2:
        cv.putText(image, "MODE:" + mode_string[mode - 1], (10, 90),
                   cv.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1,
                   cv.LINE_AA)
        if 0 <= number <= 99:
            cv.putText(image, "NUM:" + str(number), (10, 110),
                       cv.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1,
                       cv.LINE_AA)
    return image


if __name__ == '__main__':
    main()
