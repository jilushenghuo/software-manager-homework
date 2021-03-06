#!/usr/bin/env python3
# 人脸信息采集
import re
import string
import cv2
import pymysql
import shutil
from PyQt5.QtCore import QTimer, QRegExp, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap, QIcon, QRegExpValidator
from PyQt5.QtWidgets import QDialog, QApplication, QWidget, QMessageBox, QFileDialog
from PyQt5.uic import loadUi
import logging
import logging.config
import queue
import os
import sys
import xlrd
import random

class RecordDisturbance(Exception):
    pass
class OperationCancel(Exception):
    pass
class DataRecordUI(QWidget):
    receiveLogSignal = pyqtSignal(str)
    messagebox_signal = pyqtSignal(dict)
    # 日志队列
    logQueue = queue.Queue()

    def __init__(self):
        super(DataRecordUI, self).__init__()
        loadUi('./ui/DataRecord.ui', self)  # 读取UI布局
        self.setWindowIcon(QIcon('./pics/1.png'))
        self.setFixedSize(1528, 856)
        # open cv 摄像头
        self.cap = cv2.VideoCapture()
        # 图像捕获
        self.isExternalCameraUsed = False
        self.useExternalCameraCheckBox.stateChanged.connect(
            lambda: self.useExternalCamera(self.useExternalCameraCheckBox))

        self.startWebcamButton.toggled.connect(self.startWebcam)
        self.startWebcamButton.setCheckable(True)
        # 定时器
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.updateFrame)

        # 人脸检测
        self.isFaceDetectEnabled = False
        self.enableFaceDetectButton.toggled.connect(self.enableFaceDetect)
        self.enableFaceDetectButton.setCheckable(True)

        # 数据库
        self.datasets = './datasets'
        self.isDbReady = False
        self.initDbButton.setIcon(QIcon('./pics/warning.png'))
        self.initDbButton.clicked.connect(self.initDb)

        # 用户信息
        self.isUserInfoReady = False
        self.userInfo = {'stu_id': '',
                         'cn_name': '',
                         'stu_sex': '',
                         'major': ''}
        self.addOrUpdateUserInfoButton.clicked.connect(self.addOrUpdateUserInfo)
        self.migrateToDbButton.clicked.connect(self.migrateToDb)
        # 人脸采集
        self.startFaceRecordButton.clicked.connect(
            lambda: self.startFaceRecord(self.startFaceRecordButton))  # 开始人脸采集按钮绑定，并传入按钮本身用于结束状态控制
        # self.startFaceRecordButton.setCheckable(True)
        self.faceRecordCount = 0  # 已采集照片计数器
        self.minFaceRecordCount = 100  # 最少采集照片数量
        self.isFaceDataReady = False
        self.isFaceRecordEnabled = False
        self.enableFaceRecordButton.clicked.connect(self.enableFaceRecord)  # 按键绑定录入单帧图像

        self.receiveLogSignal.connect(lambda log: self.logOutput(log)) 
        self.messagebox_signal.connect(lambda log: self.message_output(log))
        self.logOutputThread = threading.Thread(target=self.receiveLog, daemon=True)
        self.logOutputThread.start()

        
        # 批量导入
        self.isImage_path_ready = False
        self.ImagepathButton.clicked.connect(self.import_image_thread)
        self.isExcel_path_ready = False
        self.ExcelpathButton.clicked.connect(self.import_excel_data)
        self.ImportPersonButton.clicked.connect(self.person_import_thread)

    @staticmethod
    def connect_to_sql():
        conn = pymysql.connect(host='localhost',
                               user='root',
                               password='123456',
                               db='mytest',
                               port=3306,
                               charset='utf8')
        cursor = conn.cursor()
        return conn, cursor

    def import_person_imageset(self):
        if self.isUserInfoReady:  # 学生信息确认
            stu_id = self.userInfo.get('stu_id')
            self.ImportPersonButton.setIcon(QIcon('./icons/success.png'))
            image_paths = QFileDialog.getOpenFileNames(self, '选择图片',
                                                       "./",
                                                       'JEPG files(*.jpg);;PNG files(*.PNG)')
            if not os.path.exists('{}/stu_{}'.format(self.datasets, stu_id)):
                os.makedirs('{}/stu_{}'.format(self.datasets, stu_id))
            image_paths = image_paths[0]
            for index, path in enumerate(image_paths):
                try:
                    img = cv2.imread(path)
                    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)  # 灰度图
                    faces = self.faceCascade.detectMultiScale(gray, 1.3, 5, minSize=(90, 90))  # 分类器侦测人脸
                    if len(faces) == 0:
                        self.logQueue.put('图片{}中没有检测到人脸！'.format(path))
                        continue
                    for (x, y, w, h) in faces:
                        if len(faces) > 1:
                            raise RecordDisturbance
                        cv2.imwrite('{}/stu_{}/img.{}-{}.jpg'.format(self.datasets, stu_id, index, ''.join(
                            random.sample(string.ascii_letters + string.digits, 4))),
                                    img[y - 20:y + h + 20, x - 20:x + w + 20])  # 灰度图的人脸区域
                except RecordDisturbance:
                    logging.error('检测到多张人脸或环境干扰')
                    self.logQueue.put('Warning：检测到图片{}存在多张人脸或环境干扰，已忽略。'.format(path))
                    continue
                except Exception as e:
                    logging.error('写入人脸图像文件到计算机过程中发生异常')
                    self.logQueue.put('Error：无法保存人脸图像，导入该图片失败')
                    print(e)
            self.migrateToDbButton.setEnabled(True)  # 允许提交至数据库
            self.isFaceDataReady = True
        else:
            self.ImportPersonButton.setIcon(QIcon('./pics/error.png'))
            self.ImportPersonButton.setChecked(False)
            self.logQueue.put('Error：操作失败，系统未检测到有效的用户信息')

    # 表格导入学生信息
    def import_excel_data(self):

        excel_paths = QFileDialog.getOpenFileNames(self, '选择表格',
                                                   "./",
                                                   'EXCEL 文件 (*.xlsx;*.xls;*.xlm;*.xlt;*.xlsm;*.xla)')
        excel_paths = excel_paths[0]
        conn, cursor = self.connect_to_sql()
        error_count = 0
        for path in excel_paths:
            sheets_file = xlrd.open_workbook(path)
            for index, sheet in enumerate(sheets_file.sheets()):
                self.logQueue.put("正在读取文件：" + str(path) + "的第" + str(index) + "个sheet表的内容...")
                for row in range(sheet.nrows):
                    row_data = sheet.row_values(row)
                    if row_data[2] == '姓名':
                        continue
                    self.userInfo['stu_id'] = row_data[1]
                    self.userInfo['cn_name'] = row_data[2]
                    self.userInfo['stu_sex'] = row_data[3]
                    self.userInfo['major'] = row_data[4]
                    try:
                        stu_id = row_data[1]
                        if not os.path.exists('{}/stu_{}'.format(self.datasets, stu_id)):
                            os.makedirs('{}/stu_{}'.format(self.datasets, stu_id))
                        db_user_count = self.commit_to_database(cursor)
                        self.dbUserCountLcdNum.display(db_user_count)  # 数据库人数计数器
                    except Exception as e:
                        print(e)
                        logging.error('读写数据库异常，无法向数据库插入/更新记录')
                        self.logQueue.put('Error：读写数据库异常，同步失败')
                        error_count += 1
                self.logQueue.put('导入完毕！其中导入失败 {} 条信息'.format(error_count))
        cursor.close()
        conn.commit()
        conn.close()

    def person_import_thread(self):
        if self.isUserInfoReady:  # 学生信息确认
            stu_id = self.userInfo.get('stu_id')
            self.ImportPersonButton.setIcon(QIcon('./pics/success.png'))
            image_paths = QFileDialog.getOpenFileNames(self, '选择图片',
                                                       "./",
                                                       'JEPG files(*.jpg);;PNG files(*.PNG)')
            self.image_paths = image_paths[0]
            if len(self.image_paths) != 0:
                if not os.path.exists('{}/stu_{}'.format(self.datasets, stu_id)):
                    os.makedirs('{}/stu_{}'.format(self.datasets, stu_id))
                self.migrateToDbButton.setEnabled(True)  # 允许提交至数据库
                self.isFaceDataReady = True

        else:
            self.ImportPersonButton.setIcon(QIcon('./pics/error.png'))
            self.ImportPersonButton.setChecked(False)
            self.logQueue.put('Error：操作失败，系统未检测到有效的用户信息')


    def import_images_data(self):
        image_paths = QFileDialog.getOpenFileNames(self, '选择图片',
                                                   "./",
                                                   'JEPG files(*.jpg);;PNG files(*.PNG)')
        image_paths = image_paths[0]
        error_count = 0
        self.logQueue.put('开始读取图片数据...')
        for index, path in enumerate(image_paths):
            stu_id = os.path.split(path)[1].split('.')[0]
            # print(stu_id)
            if not os.path.exists('{}/stu_{}'.format(self.datasets, stu_id)):
                text = '命名错误！'
                informativeText = '<b>文件 <font color=red>{}</font> 存在问题，数据库中没有以该图片名为学号的用户。</b>'.format(path)
                DataRecordUI.callDialog(QMessageBox.Critical, text, informativeText, QMessageBox.Ok)
                error_count += 1
                continue
            dstpath = '{}/stu_{}/img.{}.jpg'.format(self.datasets, stu_id, stu_id + '-0')
            try:
                shutil.copy(path, dstpath)
            except:
                text = '命名格式错误！'
                informativeText = '<b>文件 <font color=red>{}</font> 命名格式不正确。</b>'.format(path)
                DataRecordUI.callDialog(QMessageBox.Critical, text, informativeText, QMessageBox.Ok)
                error_count += 1
        self.logQueue.put('图片批量导入完成！其中导入失败 {} 张图片'.format(error_count))

    # 打开/关闭摄像头
    def startWebcam(self, status):
        if status:
            if not self.cap.isOpened():
                camID = 1 if self.isExternalCameraUsed else 0 + cv2.CAP_DSHOW
                self.cap.open(camID)
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                ret, frame = self.cap.read()  # 获取摄像头调用结果

                if not ret:
                    logging.error('无法调用电脑摄像头{}'.format(camID))
                    self.logQueue.put('Error：初始化摄像头失败')
                    self.cap.release()
                    self.startWebcamButton.setIcon(QIcon('./pics/error.png'))
                    self.startWebcamButton.setChecked(False)
                else:
                    self.timer.start(5)
                    self.enableFaceDetectButton.setEnabled(True)
                    self.startWebcamButton.setIcon(QIcon('./pics/success.png'))
                    self.startWebcamButton.setText('关闭摄像头')
        else:
            if self.cap.isOpened():
                if self.timer.isActive():
                    self.timer.stop()
                self.cap.release()
                self.faceDetectCaptureLabel.clear()
                self.faceDetectCaptureLabel.setText('<font color=red>摄像头未开启</font>')
                self.startWebcamButton.setText('打开摄像头')
                self.enableFaceDetectButton.setEnabled(False)
                self.startWebcamButton.setIcon(QIcon())

    # 开启/关闭人脸检测
    def enableFaceDetect(self, status):
        if self.cap.isOpened():
            if status:
                self.enableFaceDetectButton.setText('关闭人脸检测')
                self.isFaceDetectEnabled = True
            else:
                self.enableFaceDetectButton.setText('开启人脸检测')
                self.isFaceDetectEnabled = False

    # 采集当前捕获帧
    def enableFaceRecord(self):
        if not self.isFaceRecordEnabled:
            self.isFaceRecordEnabled = True

    # 开始/结束采集人脸数据
    def startFaceRecord(self, startFaceRecordButton):
        if startFaceRecordButton.text() == '开始采集人脸数据':  
            if self.isFaceDetectEnabled:
                if self.isUserInfoReady:  # 学生信息确认
                    self.addOrUpdateUserInfoButton.setEnabled(False)  # 采集人脸数据时禁用修改学生信息
                    if not self.enableFaceRecordButton.isEnabled():  # 启用单帧采集按钮
                        self.enableFaceRecordButton.setEnabled(True)
                    self.enableFaceRecordButton.setIcon(QIcon())
                    self.startFaceRecordButton.setIcon(QIcon('./pics/success.png'))
                    self.startFaceRecordButton.setText('结束当前人脸采集')  # 开始采集按钮状态修改为结束采集
                else:
                    self.startFaceRecordButton.setIcon(QIcon('./picss/error.png'))
                    self.startFaceRecordButton.setChecked(False)
                    self.logQueue.put('Error：操作失败，系统未检测到有效的用户信息')
            else:
                self.startFaceRecordButton.setIcon(QIcon('./pics/error.png'))
                self.logQueue.put('Error：操作失败，请开启人脸检测')
        else:  # 根据按钮文本信息判断是结束采集还是开始采集
            if self.faceRecordCount < self.minFaceRecordCount:
                text = '系统当前采集了 <font color=blue>{}</font> 帧图像，采集数据过少会导致较大的识别误差。'.format(self.faceRecordCount)
                informativeText = '<b>请至少采集 <font color=red>{}</font> 帧图像。</b>'.format(self.minFaceRecordCount)
                DataRecordUI.callDialog(QMessageBox.Information, text, informativeText, QMessageBox.Ok)
            else:
                text = '系统当前采集了 <font color=blue>{}</font> 帧图像，继续采集可以提高识别准确率。'.format(self.faceRecordCount)
                informativeText = '<b>你确定结束当前人脸采集吗？</b>'
                ret = DataRecordUI.callDialog(QMessageBox.Question, text, informativeText,
                                              QMessageBox.Yes | QMessageBox.No,
                                              QMessageBox.No)
                if ret == QMessageBox.Yes:
                    self.isFaceDataReady = True  # 结束采集，人脸数据准备完毕
                    if self.isFaceRecordEnabled:
                        self.isFaceRecordEnabled = False
                    self.enableFaceRecordButton.setEnabled(False)  # 结束采集，单帧采集按钮禁用
                    self.enableFaceRecordButton.setIcon(QIcon())
                    self.startFaceRecordButton.setText('开始采集人脸数据')  # 修改按钮文本为开始状态
                    self.startFaceRecordButton.setEnabled(False)  # 不可重新开始采集
                    self.startFaceRecordButton.setIcon(QIcon())
                    self.migrateToDbButton.setEnabled(True)  # 允许提交至数据库

    # 定时器，实时更新画面
    def updateFrame(self):
        ret, frame = self.cap.read()
        if ret:
            if self.isFaceDetectEnabled:  # 人脸检测
                detected_frame = self.detectFace(frame)
                self.displayImage(detected_frame)
            else:
                self.displayImage(frame)

    # 检测人脸
    def detectFace(self, frame):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) 
        faces = self.faceCascade.detectMultiScale(gray, 1.3, 5, minSize=(90, 90))  
        stu_id = self.userInfo.get('stu_id')

        #  遍历所有人脸，只允许有一个人的脸
        for (x, y, w, h) in faces:
            if self.isFaceRecordEnabled:
                try:  # 创建学号对应的图片数据集
                    if not os.path.exists('{}/stu_{}'.format(self.datasets, stu_id)):
                        os.makedirs('{}/stu_{}'.format(self.datasets, stu_id))
                    if len(faces) > 1:
                        raise RecordDisturbance

                    cv2.imwrite('{}/stu_{}/img.{}.jpg'.format(self.datasets, stu_id, self.faceRecordCount + 1),
                                frame[y - 20:y + h + 20, x - 20:x + w + 20])  
                except RecordDisturbance:
                    self.isFaceRecordEnabled = False
                    logging.error('检测到多张人脸或环境干扰')
                    self.logQueue.put('Warning：检测到多张人脸或环境干扰，请解决问题后继续')
                    self.enableFaceRecordButton.setIcon(QIcon('./pics/warning.png'))
                    continue
                except Exception as e:
                    logging.error('写入人脸图像文件到计算机过程中发生异常')
                    self.enableFaceRecordButton.setIcon(QIcon('./pics/error.png'))
                    self.logQueue.put('Error：无法保存人脸图像，采集当前捕获帧失败')
                else:
                    self.enableFaceRecordButton.setIcon(QIcon('./pics/success.png'))
                    self.faceRecordCount = self.faceRecordCount + 1
                    self.isFaceRecordEnabled = False  # 单帧拍摄完成后马上关闭
                    self.faceRecordCountLcdNum.display(self.faceRecordCount)  # 更新采集数量
            cv2.rectangle(frame, (x - 5, y - 10), (x + w + 5, y + h + 10), (0, 0, 255), 2) 
        return frame

    # 显示图像
    def displayImage(self, img):
        # BGR -> RGB
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        # default：The image is stored using 8-bit indexes into a colormap， for example：a gray image
        # img = cv2.flip(img, 1)
        qformat = QImage.Format_Indexed8

        if len(img.shape) == 3:  # rows[0], cols[1], channels[2]
            if img.shape[2] == 4:
                qformat = QImage.Format_RGBA8888
            else:
                qformat = QImage.Format_RGB888

        outImage = QImage(img, img.shape[1], img.shape[0], img.strides[0], qformat)
        self.faceDetectCaptureLabel.setPixmap(QPixmap.fromImage(outImage))
        self.faceDetectCaptureLabel.setScaledContents(True)  # 图片自适应大小

    # 检查数据库表是否存在
    @staticmethod
    def table_exists(cur, table_name):
        sql = "show tables;"
        cur.execute(sql)
        tables = [cur.fetchall()]
        table_list = re.findall('(\'.*?\')', str(tables))
        table_list = [re.sub("'", '', each) for each in table_list]
        if table_name in table_list:
            return True  # 存在返回1
        else:
            return False  # 不存在返回0

    # 检查数据库
    def initDb(self):
        conn, cursor = self.connect_to_sql()

        try:
            if not self.table_exists(cursor, 'users'):
                create_table_sql = '''CREATE TABLE IF NOT EXISTS users (
                                              stu_id VARCHAR(20) PRIMARY KEY NOT NULL,
                                              face_id INTEGER DEFAULT -1,
                                              cn_name VARCHAR(30) NOT NULL,
                                              major VARCHAR(40) NOT NULL,
                                              sex int(2) DEFAULT NULL,
                                              total_course_count INT DEFAULT 0,
                                              total_attendance_times INT NOT NULL DEFAULT 0,
                                              created_time DATETIME DEFAULT CURRENT_TIMESTAMP
                                              )
                                          '''
                cursor.execute(create_table_sql)
            # 查询数据表记录数
            cursor.execute('SELECT Count(*) FROM users')
            result = cursor.fetchone()
            db_user_count = result[0]
        except Exception as e:
            logging.error('读取数据库异常，无法完成数据库初始化')
            self.isDbReady = False
            self.initDbButton.setIcon(QIcon('./pics/error.png'))
            self.logQueue.put('Error：初始化数据库失败')
            print(e)
        else:
            self.isDbReady = True
            self.dbUserCountLcdNum.display(db_user_count)
            self.logQueue.put('Success：数据库初始化完成')
            self.initDbButton.setIcon(QIcon('./pics/success.png'))
            self.initDbButton.setEnabled(False)
            self.addOrUpdateUserInfoButton.setEnabled(True)
            self.ExcelpathButton.setEnabled(True)
            self.ImagepathButton.setEnabled(True)
        finally:
            cursor.close()
            conn.commit()
            conn.close()

    # 通过对话框输入增加/修改用户信息
    def addOrUpdateUserInfo(self):
        self.userInfoDialog = UserInfoDialog()  # 用户信息窗口实例
        # 获取上次输入内容
        stu_id = self.userInfo.get('stu_id')
        cn_name = self.userInfo.get('cn_name')
        major = self.userInfo.get('major')
        stu_sex = self.userInfo.get('stu_sex')
        # 填充上次输入内容到对话框中
        self.userInfoDialog.stuIDLineEdit.setText(stu_id)
        self.userInfoDialog.cnNameLineEdit.setText(cn_name)
        self.userInfoDialog.MajorLineEdit.setText(major)
        self.userInfoDialog.SexLineEdit.setText(stu_sex)
        # 保存输入信息
        self.userInfoDialog.okButton.clicked.connect(self.checkToApplyUserInfo)
        self.userInfoDialog.exec()

    # 校验用户信息并提交
    def checkToApplyUserInfo(self):
        # 不符合校验条件，输出提示
        if not self.userInfoDialog.stuIDLineEdit.hasAcceptableInput():
            self.userInfoDialog.msgLabel.setText('<font color=red>你的学号输入有误，提交失败，请检查并重试！</font>')
        elif not self.userInfoDialog.cnNameLineEdit.hasAcceptableInput():
            self.userInfoDialog.msgLabel.setText('<font color=red>你的姓名输入有误，提交失败，请检查并重试！</font>')
        elif not self.userInfoDialog.SexLineEdit.hasAcceptableInput():
            self.userInfoDialog.msgLabel.setText('<font color=red>你的性别输入有误，提交失败，请检查并重试！</font>')
        elif not self.userInfoDialog.MajorLineEdit.hasAcceptableInput():
            self.userInfoDialog.msgLabel.setText('<font color=red>你的专业输入有误，提交失败，请检查并重试！</font>')
        else:
            # 获取用户输入
            self.userInfo['stu_id'] = self.userInfoDialog.stuIDLineEdit.text().strip()
            self.userInfo['cn_name'] = self.userInfoDialog.cnNameLineEdit.text().strip()
            self.userInfo['stu_sex'] = self.userInfoDialog.SexLineEdit.text().strip()
            self.userInfo['major'] = self.userInfoDialog.MajorLineEdit.text().strip()

            # 录入端对话框信息确认
            stu_id = self.userInfo.get('stu_id')
            cn_name = self.userInfo.get('cn_name')
            major = self.userInfo.get('major')
            stu_sex = self.userInfo.get('stu_sex')
            self.stuIDLineEdit.setText(stu_id)
            self.cnNameLineEdit.setText(cn_name)
            self.MajorLineEdit.setText(major)
            self.SexLineEdit.setText(stu_sex)
            # 输入并保存合法的学生信息后允许使用人脸采集按钮
            self.isUserInfoReady = True
            if not self.startFaceRecordButton.isEnabled():
                self.startFaceRecordButton.setEnabled(True)
            self.migrateToDbButton.setIcon(QIcon())
            # 关闭对话框
            self.userInfoDialog.close()

    # 提交数据至数据库
    def commit_to_database(self, cursor):
        stu_id = self.userInfo.get('stu_id')
        cn_name = self.userInfo.get('cn_name')
        en_name = self.userInfo.get('en_name')
        major = self.userInfo.get('major')
        stu_sex = 1 if self.userInfo.get('stu_sex') == '男' else 0
        cursor.execute('SELECT * FROM users WHERE stu_id=%s', (stu_id,))
        if cursor.fetchall():
            text = '数据库已存在学号为 <font color=blue>{}</font> 的用户记录。'.format(stu_id)
            informativeText = '<b>是否覆盖？</b>'
            ret = DataRecordUI.callDialog(QMessageBox.Warning, text, informativeText,
                                          QMessageBox.Yes | QMessageBox.No)
            if ret == QMessageBox.Yes:
                # 更新已有记录
                cursor.execute(
                    'UPDATE users SET cn_name=%s,major=%s, sex=%s,  WHERE stu_id=%s',
                    (cn_name, major, stu_sex, stu_id))
            else:
                raise OperationCancel  # 记录取消覆盖操作
        else:
            # 插入新记录
            cursor.execute(
                'INSERT INTO users (stu_id, cn_name,  major, sex, ) VALUES ( %s, %s, %s, %s)',
                (stu_id, cn_name, major,  stu_sex))

        cursor.execute('SELECT Count(*) FROM users')
        result = cursor.fetchone()
        return result[0]

    # 同步用户信息到数据库
    def migrateToDb(self):
        # 仅有人脸数据录入完毕之后才能提交学生信息
        if self.isFaceDataReady:
            stu_id = self.userInfo.get('stu_id')
            cn_name = self.userInfo.get('cn_name')
            conn, cursor = self.connect_to_sql()
            try:
                db_user_count = self.commit_to_database(cursor)
            except OperationCancel:
                pass
            except Exception as e:
                print(e)
                logging.error('读写数据库异常，无法向数据库插入/更新记录')
                self.migrateToDbButton.setIcon(QIcon('./pics/error.png'))
                self.logQueue.put('Error：读写数据库异常，同步失败')
            else:
                text = '<font color=blue>{}</font> 已添加/更新到数据库。'.format(stu_id)
                informativeText = '<b><font color=blue>{}</font> 的人脸数据采集已完成！</b>'.format(cn_name)
                DataRecordUI.callDialog(QMessageBox.Information, text, informativeText, QMessageBox.Ok)

                # 清空用户信息缓存
                for key in self.userInfo.keys():
                    self.userInfo[key] = ''
                self.isUserInfoReady = False
                self.faceRecordCount = 0
                self.isFaceDataReady = False  # 人脸信息采集完成标志
                self.faceRecordCountLcdNum.display(self.faceRecordCount)  # 人脸采集计数器
                self.dbUserCountLcdNum.display(db_user_count)  # 数据库人数计数器
                # 清空确认信息
                self.stuIDLineEdit.clear()
                self.cnNameLineEdit.clear()
                self.MajorLineEdit.clear()
                self.SexLineEdit.clear()
                self.migrateToDbButton.setIcon(QIcon('./pics/success.png'))
                # 允许继续增加新用户
                self.addOrUpdateUserInfoButton.setEnabled(True)
                self.migrateToDbButton.setEnabled(False)
            finally:
                cursor.close()
                conn.commit()
                conn.close()
        else:
            self.logQueue.put('Error：操作失败，你尚未完成人脸数据采集')
            self.migrateToDbButton.setIcon(QIcon('./pics/error.png'))

    @staticmethod
    def message_output(log):
        text, informative_text = log.get('text'), log.get('informativeText')
        # print(text, informative_text)
        DataRecordUI.callDialog(QMessageBox.Information, text, informative_text, QMessageBox.Ok)

    # 系统对话框
    @staticmethod
    def callDialog(icon, text, informativeText, standardButtons, defaultButton=None):
        msg = QMessageBox()
        msg.setWindowIcon(QIcon('./pics/icon.png'))
        msg.setWindowTitle('Face Recognition System - infoCollect')
        msg.setIcon(icon)
        msg.setText(text)  # 对话框文本信息
        msg.setInformativeText(informativeText)  # 对话框详细信息
        msg.setStandardButtons(standardButtons)
        if defaultButton:
            msg.setDefaultButton(defaultButton)
        return msg.exec()

    # 窗口关闭事件，关闭定时器、摄像头
    def closeEvent(self, event):
        if self.timer.isActive():  # 关闭定时器
            self.timer.stop()
        if self.cap.isOpened():  # 关闭摄像头
            self.cap.release()
        event.accept()

# 用户信息填写对话框
class UserInfoDialog(QDialog):

    def __init__(self):
        super(UserInfoDialog, self).__init__()
        loadUi('./ui/UserInfoDialog.ui', self)  # 读取UI布局
        self.setWindowIcon(QIcon('./pics/1.png'))
        self.setFixedSize(613, 593)

        # 使用正则表达式限制用户输入
        stu_id_regx = QRegExp('^[0-11]{12}$')  # 12位学号
        stu_id_validator = QRegExpValidator(stu_id_regx, self.stuIDLineEdit)
        self.stuIDLineEdit.setValidator(stu_id_validator)

        cn_name_regx = QRegExp('^[\u4e00-\u9fa5]{1,10}$')  # 姓名，只允许输入汉字
        cn_name_validator = QRegExpValidator(cn_name_regx, self.cnNameLineEdit)
        self.cnNameLineEdit.setValidator(cn_name_validator)

        major_regx = QRegExp('^[\u4e00-\u9fa5]{1,20}$')  # 专业，只允许输入汉字
        major_validator = QRegExpValidator(major_regx, self.MajorLineEdit)
        self.MajorLineEdit.setValidator(major_validator)

        sex_regx = QRegExp('^[男|女]{1}$')  # 性别，只允许输入汉字
        sex_validator = QRegExpValidator(sex_regx, self.SexLineEdit)
        self.SexLineEdit.setValidator(sex_validator)

if __name__ == '__main__':
    logging.config.fileConfig('./logging.cfg')
    app = QApplication(sys.argv)
    window = DataRecordUI()
    window.show()
    sys.exit(app.exec())
