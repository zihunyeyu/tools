import requests
import json
import urllib.parse
from typing import List, Dict, Optional, Any


class PvfUtilityApi:
    """pvfUtility WebApi 调用工具类"""

    def __init__(self, host: str = "localhost", port: int = None):
        """
        初始化API客户端
        :param host: 服务器地址，默认localhost
        :param port: 端口号，若为空则URL不带端口
        """
        self.host = host
        self.port = port
        self.base_url = self._build_base_url()
        self.session = requests.Session()
        # 设置超时时间（秒）
        self.timeout = 30

    def _build_base_url(self) -> str:
        """构建基础URL"""
        if self.port:
            return f"http://{self.host}:{self.port}/Api/PvfUtiltiy"
        return f"http://{self.host}/Api/PvfUtiltiy"

    def _request(self, method: str, endpoint: str, params: dict = None, data: Any = None) -> Dict:
        """
        通用请求方法
        :param method: GET/POST
        :param endpoint: 接口端点（如/getVersion）
        :param params: GET参数
        :param data: POST数据
        :return: 解析后的JSON结果
        """
        url = f"{self.base_url}{endpoint}"

        try:
            if method.upper() == "GET":
                response = self.session.get(url, params=params, timeout=self.timeout)
            elif method.upper() == "POST":
                headers = {"Content-Type": "application/json"}
                response = self.session.post(
                    url,
                    params=params,
                    data=json.dumps(data, ensure_ascii=False) if data else None,
                    headers=headers,
                    timeout=self.timeout
                )
            else:
                raise ValueError(f"不支持的请求方法: {method}")

            # 检查响应状态
            response.raise_for_status()
            result = response.json()

            # 统一处理返回结果
            if result.get("IsError", True):
                raise Exception(f"接口调用失败: {result.get('Msg', '未知错误')}")
            return result

        except requests.exceptions.RequestException as e:
            raise Exception(f"网络请求异常: {str(e)}")
        except json.JSONDecodeError as e:
            raise Exception(f"JSON解析失败: {str(e)}")
        except Exception as e:
            raise Exception(f"接口调用错误: {str(e)}")

    # ==================== 基础接口 ====================
    def get_version(self) -> str:
        """获取pvfUtility版本号"""
        result = self._request("GET", "/getVersion")
        return result["Data"]

    def get_pvf_root_directory(self) -> List[str]:
        """获取Pvf根目录列表"""
        result = self._request("GET", "/getPvfRootDirectory")
        return result["Data"]

    def get_all_lst_file_list(self) -> List[str]:
        """获取主要的lst文件列表"""
        result = self._request("GET", "/GetAllLstFileList")
        return result["Data"]

    def get_pvf_pack_file_path(self) -> str:
        """获取当前载入的封包文件路径"""
        result = self._request("GET", "/GetPvfPackFilePath")
        return result["Data"]

    def folder_exists(self, file_path: str) -> bool:
        """判断文件夹/文件是否存在"""
        try:
            self._request("GET", "/folderExists", params={"filePath": file_path})
            return True
        except Exception:
            return False

    # ==================== 文件操作接口 ====================
    def get_file_list(self, dir_name: str, return_type: int = 1, file_type: str = None) -> List[str]:
        """
        获取文件列表
        :param dir_name: 目录名称（如equipment）
        :param return_type: 返回类型，默认1
        :param file_type: 文件后缀名（如.equ）
        """
        params = {
            "dirName": dir_name,
            "returnType": return_type
        }
        if file_type:
            params["fileType"] = file_type

        result = self._request("GET", "/GetFileList", params=params)
        return result["Data"]

    def get_file_content(
            self,
            file_path: str,
            use_compatible_decompiler: bool = False,
            encoding_type: str = None
    ) -> str:
        """
        获取文件内容
        :param file_path: 文件路径
        :param use_compatible_decompiler: 是否使用兼容性反编译器
        :param encoding_type: 编码类型（TW/CN/KR/JP/UTF8/Unicode）
        """
        params = {
            "filePath": file_path,
            "useCompatibleDecompiler": use_compatible_decompiler
        }
        if encoding_type:
            params["encodingType"] = encoding_type

        result = self._request("GET", "/GetFileContent", params=params)
        return result["Data"]

    def get_file_contents(self, file_list: List[str], use_compatible_decompiler: bool = False,
                          encoding_type: str = None) -> Dict[str, str]:
        """
        批量获取文件内容
        :param file_list: 文件路径列表
        :param use_compatible_decompiler: 是否使用兼容性反编译器
        :param encoding_type: 编码类型
        """
        data = {
            "FileList": file_list,
            "UseCompatibleDecompiler": use_compatible_decompiler
        }
        if encoding_type:
            data["EncodingType"] = encoding_type

        result = self._request("POST", "/GetFileContents", data=data)
        return result["Data"]["FileContentData"]

    def delete_file(self, file_path: str) -> bool:
        """删除单个文件"""
        try:
            self._request("GET", "/DeleteFile", params={"filePath": file_path})
            return True
        except Exception:
            return False

    def delete_files(self, file_list: List[str]) -> List[str]:
        """
        批量删除文件
        :return: 删除失败的文件列表
        """
        result = self._request("POST", "/DeleteFiles", data=file_list)
        return result["Data"]

    def import_file(self, file_path: str, file_content: str) -> bool:
        """
        新增/覆盖文件内容
        :param file_path: 文件路径
        :param file_content: 文件内容
        """
        try:
            self._request("POST", "/ImportFile", params={"filePath": file_path}, data=file_content)
            return True
        except Exception:
            return False

    def import_files(self, file_info_list: List[Dict[str, str]]) -> List[str]:
        """
        批量新增/覆盖文件内容
        :param file_info_list: 包含FilePath和FileContent的字典列表
        :return: 上传失败的文件列表
        """
        result = self._request("POST", "/ImportFiles", data=file_info_list)
        return result["Data"]

    # ==================== 物品信息接口 ====================
    def get_item_info(self, file_path: str) -> Dict[str, Any]:
        """获取单个物品信息（名称+代码）"""
        result = self._request("GET", "/GetItemInfo", params={"filePath": file_path})
        return result["Data"]

    def get_item_infos(self, file_list: List[str]) -> Dict[str, Dict[str, Any]]:
        """批量获取物品信息"""
        result = self._request("POST", "/GetItemInfos", data=file_list)
        return result["Data"]

    def item_code_to_file_info(self, lst_names: List[str], item_code: int) -> Dict[str, str]:
        """
        通过物品代码获取文件信息
        :param lst_names: lst名称列表（如["equipment", "stackable"]）
        :param item_code: 物品代码
        """
        lst_names_str = ",".join(lst_names)
        params = {
            "lstNames": lst_names_str,
            "itemCode": item_code
        }
        result = self._request("GET", "/ItemCodeToFileInfo", params=params)
        return result["Data"]

    def item_codes_to_file_infos(self, lst_names: List[str], item_codes: List[int]) -> Dict[str, Dict[str, str]]:
        """
        批量通过物品代码获取文件信息
        :param lst_names: lst名称列表
        :param item_codes: 物品代码列表
        """
        data = {
            "lstNames": lst_names,
            "ItemCodes": item_codes
        }
        result = self._request("POST", "/ItemCodesToFileInfos", data=data)
        return result["Data"]["Infos"]

    def get_lst_file_info(self, file_path: str) -> Dict[int, Dict[str, Any]]:
        """获取lst文件信息"""
        result = self._request("GET", "/getLstFileInfo", params={"filePath": file_path})
        return result["Data"]

    # ==================== 搜索接口 ====================
    def search_pvf(
            self,
            keyword: str,
            search_folder: str = "",
            type_: int = 1,
            source_type: int = 0,
            normal_using: int = 1,
            is_start_match: bool = False,
            script_content_search_mode: int = 1,
            is_use_like_search_path: bool = False,
            trait: bool = False,
            use_regular_expression: bool = False,
            whole_word_match: bool = False,
            remove_or_keep: int = 1,
            file_types_string: str = None,
            script_content: str = "",
            script_content_start: str = "",
            script_content_stop: str = ""
    ) -> List[str]:
        """
        搜索PVF
        :param keyword: 搜索关键词
        """
        data = {
            "SearchFolder": search_folder,
            "Keyword": keyword,
            "Type": type_,
            "SourceType": source_type,
            "NormalUsing": normal_using,
            "IsStartMatch": is_start_match,
            "SearchResult": None,
            "ScriptContentSearchMode": script_content_search_mode,
            "IsUseLikeSearchPath": is_use_like_search_path,
            "Trait": trait,
            "UseRegularExpression": use_regular_expression,
            "WholeWordMatch": whole_word_match,
            "RemoveOrKeep": remove_or_keep,
            "FileTypesString": file_types_string,
            "ScriptContent": script_content,
            "ScriptContentStart": script_content_start,
            "ScriptContentStop": script_content_stop
        }
        result = self._request("POST", "/SearchPvf", data=data)
        return result["Data"]

    # ==================== 图标接口 ====================
    def get_file_icon(self, file_path: str) -> str:
        """获取文件图标（Base64字符串）"""
        result = self._request("GET", "/getFileIcon", params={"filePath": file_path})
        return result["Data"]

    def files_to_icon_base64(self, file_list: List[str]) -> Dict[str, str]:
        """批量获取文件图标"""
        result = self._request("POST", "/filesToIconBase64", data=file_list)
        return result["Data"]

    # ==================== 其他接口 ====================
    def save_as_pvf_file(self, file_path: str) -> bool:
        """PVF封包另存为"""
        # 路径URL编码
        encoded_path = urllib.parse.quote(file_path)
        try:
            self._request("GET", "/SaveAsPvfFile", params={"filePath": encoded_path})
            return True
        except Exception:
            return False

    def go_to_tree_list_node(self, file_path: str, open_text_document: int = 0) -> bool:
        """转到文件资源管理器，可选打开编辑器"""
        try:
            self._request("GET", "/goToTreeListNode", params={
                "filePath": file_path,
                "openTextDocument": open_text_document
            })
            return True
        except Exception:
            return False

    def get_string_table(self) -> List[str]:
        """获取字符串表（stringtable.bin明文）"""
        result = self._request("GET", "/getStringTable")
        return result["Data"]


if __name__ == "__main__":
    # 初始化API客户端（根据实际端口调整，若不需要端口则不传）
    api = PvfUtilityApi(host="localhost", port=27000)

    try:
        # 1. 获取版本号
        version = api.get_version()
        print(f"pvfUtility版本: {version}")

        # 2. 获取根目录列表
        root_dirs = api.get_pvf_root_directory()
        print(f"\nPVF根目录: {root_dirs[:5]}...")  # 打印前5个

        # 3. 获取equipment目录下的.equ文件列表
        file_list = api.get_file_list(dir_name="equipment", file_type=".equ").split('\r\n')
        print(f"\nequipment目录下.equ文件数: {len(file_list)}")
        print(f"前3个文件: {file_list[:3]}")

        # # 4. 获取单个文件内容
        # if file_list:
        #     file_content = api.get_file_content(file_path=file_list[0])
        #     print(f"\n{file_list[0]} 内容前200字符: {file_content[:200]}...")
        #
        # # 5. 获取物品信息
        # item_file = "equipment/character/common/amulet/100300001.equ"
        # item_info = api.get_item_info(file_path=item_file)
        # print(f"\n物品信息: {item_info}")
        #
        # # 6. 通过物品代码查询文件信息
        # code_info = api.item_code_to_file_info(lst_names=["equipment"], item_code=100300001)
        # print(f"\n物品代码100300001信息: {code_info}")
        #
        # # 7. 搜索PVF（示例：搜索包含[width]的文件）
        # search_result = api.search_pvf(keyword="[width]")
        # print(f"\n搜索[width]结果数: {len(search_result)}")
        # print(f"前3个结果: {search_result[:3]}")
        #
        # # 8. 获取文件图标（Base64）
        # icon_base64 = api.get_file_icon(file_path=item_file)
        # print(f"\n{item_file} 图标Base64长度: {len(icon_base64)}")

    except Exception as e:
        print(f"调用失败: {e}")