/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type Emulator2PhoneRestoreOut = {
    /**
     * 状态码
     */
    code?: number;
    /**
     * 操作状态
     */
    status?: string;
    /**
     * 操作消息
     */
    message?: string;
    /**
     * 是否恢复成功
     */
    ok?: boolean;
    /**
     * 失败原因枚举: path_not_found 找不到路径 / not_phone 不是真机路径 / not_ignored 这台手机不在已移除名单里
     */
    reason?: string;
    /**
     * 恢复后的设备号, 沿用移除前的
     */
    slot?: string;
};

