/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type Emulator2PhoneAddressAddOut = {
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
     * 是否添加成功
     */
    ok?: boolean;
    /**
     * 失败原因枚举: invalid_address 地址格式不对 / path_not_found 找不到路径 / not_phone 不是真机路径
     */
    reason?: string;
    /**
     * 这台手机的设备号
     */
    slot?: string;
    /**
     * 规范化后的地址
     */
    address?: string;
    /**
     * 添加时是否已连上并认出是哪台手机; 否则显示为离线, 启动时再连
     */
    identified?: boolean;
};

