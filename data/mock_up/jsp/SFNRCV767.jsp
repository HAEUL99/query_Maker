<%-- 수납 마감자료 조회 --%>
<%-- Screen-ID: SFNRCV767 --%>
<%-- Screen-Name: 수납 마감자료 조회 --%>
<%@ page language="java" contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>
<%
    /* 조회 서비스 호출 */
    String serviceNm = "SFNRCV767SV";

    DataSet dsParam = new DataSet();
    dsParam.addColumn("P_STDD_YM",        DataTypes.STRING);
    dsParam.addColumn("P_SUPT_OBJT_DUSN", DataTypes.STRING);
    dsParam.addColumn("P_LOAN_SUBJ_DVSN", DataTypes.STRING);

    ServiceResult result = ServiceFactory.callService(serviceNm, dsParam);
%>
