/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type QueueConfig_Info = {
    /**
     * 队列名称
     */
    Name?: (string | null);
    /**
     * 是否启用定时
     */
    TimeEnabled?: (boolean | null);
    /**
     * 是否启动时运行
     */
    StartUpEnabled?: (boolean | null);
    /**
     * 完成后操作
     */
    AfterAccomplish?: ('NoAction' | 'Shutdown' | 'ShutdownForce' | 'Reboot' | 'Hibernate' | 'Sleep' | 'KillSelf' | null);
    /**
     * 是否在队列开始前执行脚本
     */
    IfScriptBeforeQueue?: (boolean | null);
    /**
     * 队列前脚本路径
     */
    ScriptBeforeQueue?: (string | null);
    /**
     * 是否在队列结束后执行脚本
     */
    IfScriptAfterQueue?: (boolean | null);
    /**
     * 队列后脚本路径
     */
    ScriptAfterQueue?: (string | null);
};

