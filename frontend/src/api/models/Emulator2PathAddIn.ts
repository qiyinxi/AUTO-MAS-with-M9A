/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type Emulator2PathAddIn = {
    /**
     * 配置ID
     */
    emulatorId: string;
    /**
     * 模拟器安装目录; 真机为 adb.exe 或它所在的文件夹
     */
    installPath: string;
    /**
     * 安装别名
     */
    alias?: (string | null);
    /**
     * 设备类型, 留空按目录猜; 真机(phone)必须指定, 雷电 / MuMu 目录里也有 adb.exe
     */
    type?: (string | null);
};

