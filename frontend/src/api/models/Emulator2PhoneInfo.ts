/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 真机的附加信息。模拟器没有这一项。
 */
export type Emulator2PhoneInfo = {
    /**
     * 手机序列号; 还没连上过的无线地址为空
     */
    serial?: string;
    /**
     * 手机型号
     */
    model?: string;
    /**
     * 当前连接方式: usb / wifi / 空串表示没有连接
     */
    connection?: string;
    /**
     * adb 报告的连接状态, 如 device / unauthorized / offline
     */
    adbState?: string;
    /**
     * 不可用的原因码: unauthorized 未授权调试 / offline 无响应 / no_permissions 无访问权限 / mode 处于特殊模式; 空串表示没有问题
     */
    reason?: string;
    /**
     * 记住的无线调试地址
     */
    wifiAddress?: string;
};

