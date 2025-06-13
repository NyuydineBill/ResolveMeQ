from rest_framework import permissions

from rest_framework import permissions


class IsSuperAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        return bool(request.user.is_super_admin or request.user.is_superuser)


class IsShopAdmin(permissions.BasePermission):

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        return bool( request.user.is_shop_admin or request.user.is_superuser or request.user.is_super_admin)


class IsShopAdminOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        return bool( request.user.is_shop_admin)



class IsWareHouseAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        return bool(request.user.is_warehouse_admin or request.user.is_superuser or request.user.is_super_admin)


class IsOwnerOrReadOnly(permissions.BasePermission):

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.owner == request.user