NAVIGATION = [
    {"label": "系统概览", "url": "core:dashboard"},
    {
        "label": "映射管理",
        "children": [
            {"label": "端口映射", "url": "mappings:port-list", "permission": "mappings.view_portmapping"},
            {"label": "域名映射", "url": "mappings:domain-list", "permission": "mappings.view_domainmapping"},
        ],
    },
    {
        "label": "资产管理",
        "children": [
            {"label": "虚拟机", "url": "assets:vm-list", "permission": "assets.view_virtualmachine"},
            {"label": "物理机", "url": "assets:host-list", "permission": "assets.view_physicalhost"},
            {"label": "NameSpace", "url": "assets:namespace-list", "permission": "assets.view_namespace"},
            {"label": "资质管理", "url": "assets:qualification-list", "permission": "assets.view_qualificationmanagement"},
        ],
    },
    {
        "label": "BSECP",
        "children": [
            {"label": "Module管理", "url": "bsecp:module-list", "permission": "bsecp.view_module"},
            {"label": "授权查询", "url": "bsecp:authorization-list", "permission": "bsecp.view_authorizationrecord"},
            {"label": "授权详情", "url": "bsecp:authorization-detail", "permission": "bsecp.view_authorizationrecord"},
        ],
    },
    {
        "label": "行云管家",
        "children": [
            {"label": "堡垒机清单", "url": "cloudops:bastion-list", "permission": "cloudops.view_bastionhost"},
            {"label": "免登录", "url": "cloudops:ssh-proxy", "permission": "cloudops.view_bastionhost"},
        ],
    },
    {
        "label": "运维监控",
        "children": [
            {"label": "主机资源监控", "url": "monitoring:host-resource-dashboard", "permission": "monitoring.view_monitoringtarget"},
            {"label": "K8S资源监控", "url": "monitoring:k8s-resource-dashboard", "permission": "monitoring.view_monitoringtarget"},
            {"label": "定时任务监控", "url": "monitoring:task-list", "permission": "monitoring.view_scheduledtaskrecord"},
        ],
    },
    {
        "label": "系统管理",
        "children": [
            {"label": "用户管理", "url": "accounts:user-list", "permission": "accounts.view_user"},
            {"label": "角色管理", "url": "accounts:role-list", "permission": "accounts.view_role"},
            {"label": "日志管理", "url": "logs:dashboard", "permission": "logs.view_operationauditlog"},
        ],
    },
]
