"""
PVF API Client - PVF Utility Web API 客户端

封装 pvfUtility 的 HTTP API 调用。
"""

import json
import logging
import urllib.parse
from typing import List, Dict, Optional, Any, Union

import requests

from config import PVF_API_HOST, PVF_API_PORT, PVF_API_TIMEOUT

logger = logging.getLogger(__name__)


class PvfApiError(Exception):
    """PVF API 错误"""
    pass


class PvfUtilityApi:
    """pvfUtility WebApi 调用工具类"""
    
    def __init__(
        self,
        host: str = PVF_API_HOST,
        port: Optional[int] = PVF_API_PORT,
        timeout: int = PVF_API_TIMEOUT
    ):
        """
        初始化 API 客户端
        
        Args:
            host: 服务器地址
            port: 端口号，None 则 URL 不带端口
            timeout: 请求超时时间（秒）
        """
        self.host = host
        self.port = port
        self.timeout = timeout
        self.base_url = self._build_base_url()
        self.session = requests.Session()
    
    def _build_base_url(self) -> str:
        """构建基础 URL"""
        if self.port:
            return f"http://{self.host}:{self.port}/Api/PvfUtiltiy"
        return f"http://{self.host}/Api/PvfUtiltiy"
    
    def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        data: Any = None,
        headers: Optional[Dict] = None
    ) -> Dict:
        """
        通用请求方法
        
        Args:
            method: GET/POST
            endpoint: 接口端点（如 /getVersion）
            params: GET 参数
            data: POST 数据
            headers: 额外请求头
            
        Returns:
            解析后的 JSON 结果
            
        Raises:
            PvfApiError: API 调用失败
        """
        url = f"{self.base_url}{endpoint}"
        default_headers = {"Content-Type": "application/json"} if data else {}
        if headers:
            default_headers.update(headers)
        
        try:
            if method.upper() == "GET":
                response = self.session.get(
                    url, params=params, 
                    timeout=self.timeout
                )
            elif method.upper() == "POST":
                json_data = json.dumps(data, ensure_ascii=False) if data else None
                response = self.session.post(
                    url, params=params, data=json_data,
                    headers=default_headers, timeout=self.timeout
                )
            else:
                raise PvfApiError(f"不支持的请求方法: {method}")
            
            response.raise_for_status()
            result = response.json()
            
            # 统一处理返回结果
            if result.get("IsError", True):
                raise PvfApiError(f"接口调用失败: {result.get('Msg', '未知错误')}")
            
            return result
            
        except requests.exceptions.RequestException as e:
            raise PvfApiError(f"网络请求异常: {e}")
        except json.JSONDecodeError as e:
            raise PvfApiError(f"JSON 解析失败: {e}")
    
    # ==================== 基础接口 ====================
    
    def get_version(self) -> str:
        """获取 pvfUtility 版本号"""
        result = self._request("GET", "/getVersion")
        return result["Data"]
    
    def get_pvf_root_directory(self) -> List[str]:
        """获取 PVF 根目录列表"""
        result = self._request("GET", "/getPvfRootDirectory")
        return result["Data"]
    
    def get_all_lst_file_list(self) -> List[str]:
        """获取主要的 lst 文件列表"""
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
        except PvfApiError:
            return False
    
    # ==================== 文件操作接口 ====================
    
    def get_file_list(
        self,
        dir_name: str,
        return_type: int = 1,
        file_type: Optional[str] = None
    ) -> List[str]:
        """
        获取文件列表
        
        Args:
            dir_name: 目录名称（如 equipment）
            return_type: 返回类型，默认 1
            file_type: 文件后缀名（如 .equ）
        """
        params = {"dirName": dir_name, "returnType": return_type}
        if file_type:
            params["fileType"] = file_type
        
        result = self._request("GET", "/GetFileList", params=params)
        data = result["Data"]
        # 处理字符串返回格式
        if isinstance(data, str):
            return [line.strip() for line in data.split('\r\n') if line.strip()]
        return data
    
    def get_file_content(
        self,
        file_path: str,
        use_compatible_decompiler: bool = False,
        encoding_type: Optional[str] = None
    ) -> str:
        """
        获取文件内容
        
        Args:
            file_path: 文件路径
            use_compatible_decompiler: 是否使用兼容性反编译器
            encoding_type: 编码类型（TW/CN/KR/JP/UTF8/Unicode）
        """
        params = {
            "filePath": file_path,
            "useCompatibleDecompiler": use_compatible_decompiler
        }
        if encoding_type:
            params["encodingType"] = encoding_type
        
        result = self._request("GET", "/GetFileContent", params=params)
        return result["Data"]
    
    def get_file_contents(
        self,
        file_list: List[str],
        use_compatible_decompiler: bool = False,
        encoding_type: Optional[str] = None
    ) -> Dict[str, str]:
        """
        批量获取文件内容
        
        Args:
            file_list: 文件路径列表
            use_compatible_decompiler: 是否使用兼容性反编译器
            encoding_type: 编码类型
        """
        data = {
            "FileList": file_list,
            "UseCompatibleDecompiler": use_compatible_decompiler
        }
        if encoding_type:
            data["EncodingType"] = encoding_type
        
        result = self._request("POST", "/GetFileContents", data=data)
        return result["Data"].get("FileContentData", {})
    
    def delete_file(self, file_path: str) -> bool:
        """删除单个文件"""
        try:
            self._request("GET", "/DeleteFile", params={"filePath": file_path})
            return True
        except PvfApiError:
            return False
    
    def delete_files(self, file_list: List[str]) -> List[str]:
        """
        批量删除文件
        
        Returns:
            删除失败的文件列表
        """
        result = self._request("POST", "/DeleteFiles", data=file_list)
        return result["Data"]
    
    def import_file(self, file_path: str, file_content: str) -> bool:
        """
        新增/覆盖文件内容
        
        Args:
            file_path: 文件路径
            file_content: 文件内容
        """
        try:
            self._request(
                "POST", "/ImportFile",
                params={"filePath": file_path},
                data=file_content
            )
            return True
        except PvfApiError:
            return False
    
    def import_files(self, file_info_list: List[Dict[str, str]]) -> List[str]:
        """
        批量新增/覆盖文件内容
        
        Args:
            file_info_list: 包含 FilePath 和 FileContent 的字典列表
            
        Returns:
            上传失败的文件列表
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
    
    def item_code_to_file_info(
        self,
        lst_names: List[str],
        item_code: int
    ) -> Dict[str, str]:
        """
        通过物品代码获取文件信息
        
        Args:
            lst_names: lst 名称列表（如 ["equipment", "stackable"]）
            item_code: 物品代码
        """
        params = {
            "lstNames": ",".join(lst_names),
            "itemCode": item_code
        }
        result = self._request("GET", "/ItemCodeToFileInfo", params=params)
        return result["Data"]
    
    def item_codes_to_file_infos(
        self,
        lst_names: List[str],
        item_codes: List[int]
    ) -> Dict[str, Dict[str, str]]:
        """
        批量通过物品代码获取文件信息
        
        Args:
            lst_names: lst 名称列表
            item_codes: 物品代码列表
        """
        data = {"lstNames": lst_names, "ItemCodes": item_codes}
        result = self._request("POST", "/ItemCodesToFileInfos", data=data)
        return result["Data"].get("Infos", {})
    
    def get_lst_file_info(self, file_path: str) -> Dict[int, Dict[str, Any]]:
        """获取 lst 文件信息"""
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
        file_types_string: Optional[str] = None,
        script_content: str = "",
        script_content_start: str = "",
        script_content_stop: str = ""
    ) -> List[str]:
        """
        搜索 PVF
        
        Args:
            keyword: 搜索关键词
            search_folder: 搜索文件夹
            type_: 搜索类型
            source_type: 源类型
            normal_using: 常规使用标志
            is_start_match: 是否匹配开头
            script_content_search_mode: 脚本内容搜索模式
            is_use_like_search_path: 是否使用模糊搜索路径
            trait: 特征标志
            use_regular_expression: 是否使用正则表达式
            whole_word_match: 是否全词匹配
            remove_or_keep: 保留或移除标志
            file_types_string: 文件类型字符串
            script_content: 脚本内容
            script_content_start: 脚本内容起始
            script_content_stop: 脚本内容结束
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
        """获取文件图标（Base64 字符串）"""
        result = self._request("GET", "/getFileIcon", params={"filePath": file_path})
        return result["Data"]
    
    def files_to_icon_base64(self, file_list: List[str]) -> Dict[str, str]:
        """批量获取文件图标"""
        result = self._request("POST", "/filesToIconBase64", data=file_list)
        return result["Data"]
    
    # ==================== 其他接口 ====================
    
    def save_as_pvf_file(self, file_path: str) -> bool:
        """PVF 封包另存为"""
        encoded_path = urllib.parse.quote(file_path)
        try:
            self._request("GET", "/SaveAsPvfFile", params={"filePath": encoded_path})
            return True
        except PvfApiError:
            return False
    
    def go_to_tree_list_node(
        self,
        file_path: str,
        open_text_document: int = 0
    ) -> bool:
        """转到文件资源管理器，可选打开编辑器"""
        try:
            self._request("GET", "/goToTreeListNode", params={
                "filePath": file_path,
                "openTextDocument": open_text_document
            })
            return True
        except PvfApiError:
            return False
    
    def get_string_table(self) -> List[str]:
        """获取字符串表（stringtable.bin 明文）"""
        result = self._request("GET", "/getStringTable")
        return result["Data"]


def main():
    """示例用法"""
    logging.basicConfig(level=logging.INFO)
    
    api = PvfUtilityApi(host="localhost", port=27000)
    
    try:
        # 获取版本号
        version = api.get_version()
        print(f"pvfUtility 版本: {version}")
        
        # 获取根目录列表
        root_dirs = api.get_pvf_root_directory()
        print(f"\nPVF 根目录（前 5 个）: {root_dirs[:5]}")
        
        # 获取 equipment 目录下的 .equ 文件列表
        file_list = api.get_file_list(dir_name="equipment", file_type=".equ")
        print(f"\nequipment 目录下 .equ 文件数: {len(file_list)}")
        print(f"前 3 个文件: {file_list[:3]}")
        
    except PvfApiError as e:
        print(f"API 调用失败: {e}")


if __name__ == "__main__":
    main()
