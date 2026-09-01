#include "Node.h"
#include "mysql/mysql.h"

#include <cstring>
#include <string>

static long long int_arg(UDF_ARGS *args, unsigned int i) {
    if (args->args[i] == nullptr) return 0;
    return *reinterpret_cast<long long *>(args->args[i]);
}

static std::string string_arg(UDF_ARGS *args, unsigned int i) {
    if (args->args[i] == nullptr) return "";
    return std::string(args->args[i], args->lengths[i]);
}

static bool expect_args(UDF_ARGS *args, char *message, unsigned int n) {
    if (args->arg_count != n) {
        std::strcpy(message, "wrong number of arguments");
        return true;
    }
    return false;
}

extern "C" {

bool FHInsert_init(UDF_INIT *, UDF_ARGS *args, char *message) {
    if (expect_args(args, message, 2)) return true;
    args->arg_type[0] = INT_RESULT;
    args->arg_type[1] = STRING_RESULT;
    if (root == nullptr) root_initial();
    return false;
}

long long FHInsert(UDF_INIT *, UDF_ARGS *args, char *, char *) {
    if (root == nullptr) root_initial();

    int pos = static_cast<int>(int_arg(args, 0));
    std::string cipher = string_arg(args, 1);

    start_update = -1;
    end_update = -1;
    update.clear();

    return root->insert(pos, cipher);
}

bool FHSearch_init(UDF_INIT *, UDF_ARGS *args, char *message) {
    if (expect_args(args, message, 1)) return true;
    args->arg_type[0] = INT_RESULT;
    if (root == nullptr) root_initial();
    return false;
}

long long FHSearch(UDF_INIT *, UDF_ARGS *args, char *, char *) {
    if (root == nullptr) root_initial();
    int pos = static_cast<int>(int_arg(args, 0));
    return root->search(pos);
}

bool FHUpdate_init(UDF_INIT *, UDF_ARGS *args, char *message) {
    if (expect_args(args, message, 1)) return true;
    args->arg_type[0] = STRING_RESULT;
    return false;
}

long long FHUpdate(UDF_INIT *, UDF_ARGS *args, char *, char *) {
    return get_update(string_arg(args, 0));
}

bool FHStart_init(UDF_INIT *, UDF_ARGS *args, char *message) {
    if (expect_args(args, message, 0)) return true;
    return false;
}

long long FHStart(UDF_INIT *, UDF_ARGS *, char *, char *) {
    return start_update;
}

bool FHEnd_init(UDF_INIT *, UDF_ARGS *args, char *message) {
    if (expect_args(args, message, 0)) return true;
    return false;
}

long long FHEnd(UDF_INIT *, UDF_ARGS *, char *, char *) {
    return end_update;
}

bool FHReset_init(UDF_INIT *, UDF_ARGS *args, char *message) {
    if (expect_args(args, message, 0)) return true;
    return false;
}

long long FHReset(UDF_INIT *, UDF_ARGS *, char *, char *) {
    reset_all();
    return 1;
}

bool FHLeafSplits_init(UDF_INIT *, UDF_ARGS *args, char *message) {
    if (expect_args(args, message, 0)) return true;
    return false;
}

long long FHLeafSplits(UDF_INIT *, UDF_ARGS *, char *, char *) {
    return leaf_split_count;
}

bool FHInternalSplits_init(UDF_INIT *, UDF_ARGS *args, char *message) {
    if (expect_args(args, message, 0)) return true;
    return false;
}

long long FHInternalSplits(UDF_INIT *, UDF_ARGS *, char *, char *) {
    return internal_split_count;
}

bool FHTotal_init(UDF_INIT *, UDF_ARGS *args, char *message) {
    if (expect_args(args, message, 0)) return true;
    return false;
}

long long FHTotal(UDF_INIT *, UDF_ARGS *, char *, char *) {
    return total_items();
}

} // extern "C"
