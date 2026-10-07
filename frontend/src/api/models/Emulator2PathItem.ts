/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Emulator2IgnoredPhone } from './Emulator2IgnoredPhone';
export type Emulator2PathItem = {
    /**
     * 路径标识
     */
    pathId: string;
    /**
     * 安装目录
     */
    installPath: string;
    /**
     * 安装别名
     */
    alias?: string;
    /**
     * 模拟器类型
     */
    type?: string;
    /**
     * 版本号
     */
    version?: string;
    /**
     * 该路径占用的设备号
     */
    slots?: Array<string>;
    /**
     * 真机路径下用户移除过的手机, 不再自动纳管, 可以恢复; 模拟器路径为空
     */
    ignoredPhones?: Array<Emulator2IgnoredPhone>;
};

