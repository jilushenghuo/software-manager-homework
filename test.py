#-*-coding:gb2312-*-
import os
# class TestAccuracyRate():
import cv2
import face_recognition
import numpy as np


def trainImage():
    train_dir = 'rate_train_data'
    # 训练文件夹
    # 将训练文件夹下的图片放到一个列表中
    train_image_list = os.listdir(train_dir)
    print("训练图片数量：%s" % len(train_image_list))

    # 定义空列表，存放文读取的图片名称
    train_image_names_list = []
    # 存放读取的图片相对路径
    train_image_paths_list = []
    # 存放图片转化的numpy数组
    train_image_rec_list = []
    # 存放每个图片面部编码的第一个面部编码信息
    train_image_encodings_list = []
    '源文件读取训练数据'
    # 遍历列表，读取列表中的训练图片文件名
    for per_image in train_image_list:
        name = per_image.strip('.jpg')
        # print(name)
        train_image_names_list.append(name)  # 将读取的图片名称添加到预先定义好的列表中
        # 设定每幅图片的相对路径，根据路径读取每幅图片
        train_per_image_path = os.path.join(train_dir, per_image)
        train_image_paths_list.append(train_per_image_path)  # 将每幅图片的路径添加到预先定义好的列表中
        # 加载训练图像通过face_recognition学习如何识别它,将文档加载到numpy数组中,以便计算机进行识别。
        train_per_image_rec = face_recognition.load_image_file(train_per_image_path)
        train_image_rec_list.append(train_per_image_rec)
        print(train_per_image_rec[0])
        # 获取每个图像面部编码信息
        train_per_image_encoding = face_recognition.face_encodings(train_per_image_rec)[0]
        print("训练图片%s人脸检测完成"%name)
        train_image_encodings_list.append(train_per_image_encoding)
        # print(train_per_image_encoding)
    # print(train_image_names_list)
    return train_image_names_list, train_image_encodings_list


def testImage():
    # '进行测试文件的自动读取'
    # 测试图片路径
    test_dir = 'rate_test_data'  # 测试文件夹
    # 将测试图片名称读取到一个列表中
    test_image_list = os.listdir(test_dir)
    # print(test_image_list)
    # 获取测试图像总数量
    test_date_num = len(test_image_list)
    print('测试图片数量为：%s 张' % test_date_num)
    # 读取训练数据
    train_image_names_list, train_image_encodings_list = trainImage()
    print('========================')
    print("源文件读取完成。。。")
    # 设置初始人脸识别成功个数为0
    reco_count = 0  # 成功识别人脸识别数
    decate_count = 0  # 未成功识别人脸图片数
    right_reco_count = 0  # 正确匹配人脸图片数
    undecate_count = 0  # 未成功检测到人脸数量
    unsuccess_reco_count = 0  # 未成功识别人人脸数量
    unsuccess_reco_name_count = []  # 未成功识别人脸列表
    undecate_name_list = []  # 未成功检测人脸列表
    false_right_reco_name_list = []  # 识别并匹配成功，但未正确匹配人脸图片列表
    print("图像识别中。。。")
    # 遍历列表，进行测试图片处理
    for per_image in test_image_list:

        # 图像名称以人物名命名，读取人物名
        name = per_image.strip('.jpg')
        # 图像的相对路径
        test_per_image_path = os.path.join(test_dir, per_image)
        per_image_cv = cv2.imread(test_per_image_path)
        per_image_cvcolor = cv2.cvtColor(per_image_cv, cv2.COLOR_BGR2RGB)
        '此处图片没有检测到人脸时往下执行则会报错，需要在下一步之前增加判断条件：是否检测到人脸信息！'
        per_image_encoding = face_recognition.face_encodings(per_image_cvcolor)
        # print(per_image_encoding)
        '判断条件：图片人脸编码是否为空！'
        if len(per_image_encoding) > 0:
            decate_count += 1
            # 获取检测到人脸时面部编码信息中数组0位置面部编码
            per_image_encoding = per_image_encoding[0]
            "图像人脸识别部分代码，同时使用compare_faces和face_distance方法提高训练结果准确度。"
            # 根据面部编码匹配脸，布尔类型列表
            matchs_bool_list = face_recognition.compare_faces(train_image_encodings_list, per_image_encoding,                                                tolerance=0.46)
            # print(matchs_bool_list)
            # print(train_image_names_list)
            # 根据面孔之间的欧氏距离，返回一个数值列表
            face_distances_list = face_recognition.face_distance(train_image_encodings_list, per_image_encoding)
            # 根据欧式距离，查找最相似面孔的索引
            # print(face_distances_list)
            best_match_index = np.argmin(face_distances_list)
            # print(best_match_index)
            # print(train_image_names_list[best_match_index])
            print("name:%s,match_name:%s" % (name, train_image_names_list[best_match_index]))
            if matchs_bool_list[best_match_index]:
                match_name = train_image_names_list[best_match_index]
                # best_match_encoding = train_image_encodings_list[best_match_index]
                print('匹配人物姓名：%s' % match_name)
                reco_count += 1
            else:
                unsuccess_reco_count += 1
                unsuccess_reco_name = name + '.jpg'
                unsuccess_reco_name_count.append(unsuccess_reco_name)
                match_name = 'unknown_person'
            # 设置文件名相同，根据文件名测试准确识别
            if name == match_name:
                right_reco_count += 1
            else:
                false_right_reco_name = name + '.jpg'
                false_right_reco_name_list.append(false_right_reco_name)
        else:
            undecate_count += 1
            undecate_name = name + '.jpg'
            undecate_name_list.append(undecate_name)
            print("图片%s.jpg未检测到有效人脸区域,请检测上传图片是否为人脸正面区域！" % name)
    print("识别完成！")

    print("成功检测人脸图片数量：%s,未检测到人脸图片数量：%s || 成功识别成功匹配人脸数量:%s,成功识别未成功匹配到人脸图片数量%s || 正确匹配人脸图片数量：%s" % (
    decate_count, undecate_count, reco_count, unsuccess_reco_count, right_reco_count))
    print("成功识别未成功匹配到人脸图片名称列表：%s" % (unsuccess_reco_name_count))
    print("识别匹配成功，但未正确匹配人脸图片名称列表：%s" % (false_right_reco_name_list))
    print("未成功检测人脸图片名称列表：%s" % (undecate_name_list))
    reco_rate = reco_count / (test_date_num - undecate_count)
    right_reco_rate = right_reco_count / (test_date_num - undecate_count)
    print("识别完成！人脸检测成功率为：%s%%,识别准确率为：%s%%" % ((reco_rate * 100), (right_reco_rate * 100)))  # 识别准确率百分号显示
# cv2.destroyAllWindows()

if __name__ == '__main__':
    testImage()
